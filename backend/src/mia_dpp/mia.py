"""MIA composition root — document-first DPP extraction agent."""

from __future__ import annotations

import uuid

import httpx

from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.settings import ModelSettings

from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.agent.models import (
    AgentRequest,
    AgentResponse,
    AgentStatus,
    BulkExtractRequest,
    BulkExtractResponse,
    CombinedExtractionOutput,
    ExtractionOutput,
    MiaState,
    SUBMODEL_LABELS,
    SUBMODEL_REQUIRED,
    SUBMODEL_SEQUENCE,
    SubmodelStatus,
    TraceStatus,
)
from mia_dpp.agent.prompts import COMBINED_EXTRACTION_PROMPT, SUBMODEL_PROMPTS
from mia_dpp.agent.web_agents import WebAgentDeps, build_carbon_footprint_agent, build_technical_data_agent
from mia_dpp.api.schemas import SpecialistAgentRequest, SpecialistAgentResponse
from mia_dpp.config import Settings
from mia_dpp.integrations.ddgs import DdgsSearchProvider
from mia_dpp.store import SessionSnapshot, Store
from typing import Literal


class Mia:
    """Compose MIA and run document-extraction DPP agent sessions.

    The agent reads document text supplied by the frontend, extracts IDTA fields
    for the current submodel using the LLM, and returns a structured response.
    It never searches the web or invents product data.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        model: Model | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.templates = OfficialTemplateRepository(self.settings.standards_root)
        self.store = Store(
            self.settings.thread_store_path,
            artifact_root=self.settings.workspace_root,
        )

        agent_model = model
        if agent_model is None and self.settings.openrouter_api_key is not None:
            agent_model = OpenRouterModel(
                self.settings.agent_model,
                provider=OpenRouterProvider(
                    api_key=self.settings.openrouter_api_key.get_secret_value(),
                    app_url="https://mia-dpp.vercel.app",
                    app_title="MIA Digital Product Passport",
                ),
            )

        self._agents: dict[str, Agent[None, ExtractionOutput]] = {}
        self._combined_agent: Agent[None, CombinedExtractionOutput] | None = None
        self._model = agent_model

        if agent_model is not None:
            for submodel_key, instructions in SUBMODEL_PROMPTS.items():
                self._agents[submodel_key] = Agent(
                    agent_model,
                    name=f"mia-{submodel_key}",
                    output_type=ExtractionOutput,
                    instructions=instructions,
                    retries=2,
                    model_settings=ModelSettings(
                        temperature=0,
                        max_tokens=4096,
                    ),
                )
            self._combined_agent = Agent(
                agent_model,
                name="mia-combined",
                output_type=CombinedExtractionOutput,
                instructions=COMBINED_EXTRACTION_PROMPT,
                retries=2,
                model_settings=ModelSettings(
                    temperature=0,
                    max_tokens=8192,
                ),
            )
        self._carbon_footprint_agent = build_carbon_footprint_agent(agent_model) if agent_model is not None else None
        self._technical_data_agent = build_technical_data_agent(agent_model) if agent_model is not None else None
        self._search = DdgsSearchProvider()

    @property
    def configured(self) -> bool:
        """Return whether an autonomous model is available."""
        return bool(self._agents)

    async def message(self, request: AgentRequest) -> AgentResponse:
        """Load session, run extraction agent, persist results, return response."""

        thread_id = request.thread_id or f"thread-{uuid.uuid4().hex}"
        snapshot = self.store.load(thread_id)
        state = snapshot.state if snapshot is not None else MiaState(thread_id=thread_id)
        history = snapshot.history if snapshot is not None else []
        trace_offset = self.store.event_count(thread_id)

        # Merge incoming context into session state
        if request.company_name:
            state.company_name = request.company_name
        if request.company_website:
            state.company_website = request.company_website
        if request.document_filename:
            state.document_filename = request.document_filename

        # Update current submodel from request (frontend drives the sequence)
        current_submodel = request.current_submodel
        if current_submodel not in SUBMODEL_SEQUENCE:
            current_submodel = state.current_submodel

        # Handle skip action — mark current as skipped, advance
        if request.action == "skip":
            state.submodel_status[current_submodel] = SubmodelStatus.SKIPPED
            idx = list(SUBMODEL_SEQUENCE).index(current_submodel)
            if idx < len(SUBMODEL_SEQUENCE) - 1:
                current_submodel = SUBMODEL_SEQUENCE[idx + 1]
            state.current_submodel = current_submodel
            all_done = all(
                state.submodel_status.get(sm) in (SubmodelStatus.COMPLETE, SubmodelStatus.SKIPPED)
                for sm in SUBMODEL_SEQUENCE
            )
            progress = _compute_progress(state)
            self.store.save(
                SessionSnapshot(
                    state=state,
                    history=history,
                    reply="Skipped",
                    decision_summary="submodel skipped",
                )
            )
            return AgentResponse(
                thread_id=thread_id,
                reply=f"Understood — skipping that submodel. Let's move on to {_label(current_submodel)}.",
                status=AgentStatus.NEEDS_INPUT,
                current_submodel=current_submodel,
                submodel_status=dict(state.submodel_status),
                submodel_progress=progress,
                all_submodels_done=all_done,
                trace_events=self.store.list_events(thread_id, trace_offset),
            )

        # Mark current submodel as in_progress
        if state.submodel_status.get(current_submodel) == SubmodelStatus.PENDING:
            state.submodel_status[current_submodel] = SubmodelStatus.IN_PROGRESS
        state.current_submodel = current_submodel

        agent = self._agents.get(current_submodel)
        if agent is None:
            self.store.add_event(
                thread_id,
                "run.configuration_required",
                "OPENROUTER_API_KEY not configured.",
            )
            return AgentResponse(
                thread_id=thread_id,
                reply="Configure OPENROUTER_API_KEY to use the MIA agent.",
                status=AgentStatus.FAILED,
                current_submodel=current_submodel,
                submodel_status=dict(state.submodel_status),
                submodel_progress=_compute_progress(state),
                trace_events=self.store.list_events(thread_id, trace_offset),
            )

        self.store.add_event(
            thread_id,
            "run.started",
            f"MIA started extraction for {current_submodel}.",
            status=TraceStatus.STARTED,
            input_summary=(request.document_filename or request.message)[:200],
        )

        prompt = self._build_prompt(request, state, current_submodel)
        result = await agent.run(prompt, message_history=history)
        output = result.output

        # Merge extracted fields into flat dict (backward compat)
        for field in output.extracted_fields:
            state.extracted_fields[field.idta_field] = field.value

        # Also store per-submodel fields
        if current_submodel not in state.submodel_fields:
            state.submodel_fields[current_submodel] = {}
        for field in output.extracted_fields:
            state.submodel_fields[current_submodel][field.idta_field] = field.value

        # Check if current submodel is complete (all required fields found)
        required = SUBMODEL_REQUIRED.get(current_submodel, ())
        sm_fields = state.submodel_fields.get(current_submodel, {})
        submodel_complete = all(f in sm_fields for f in required)
        if submodel_complete:
            state.submodel_status[current_submodel] = SubmodelStatus.COMPLETE

        # Compute missing fields for this submodel
        missing_required = [f for f in required if f not in sm_fields]
        all_optional = [
            f for f in state.extracted_fields
            if f not in required
        ]

        # Check if all submodels are done
        all_done = all(
            state.submodel_status.get(sm) in (SubmodelStatus.COMPLETE, SubmodelStatus.SKIPPED)
            for sm in SUBMODEL_SEQUENCE
        )
        dpp_ready = state.submodel_status.get("digital_nameplate") == SubmodelStatus.COMPLETE

        state.status = AgentStatus.COMPLETED if all_done else AgentStatus.NEEDS_INPUT
        progress = _compute_progress(state)

        self.store.add_event(
            thread_id,
            "run.completed",
            (
                f"Extracted {len(output.extracted_fields)} field(s) for {current_submodel}. "
                f"Missing required: {len(missing_required)}."
            ),
            status=TraceStatus.COMPLETED,
            metadata={
                "extracted": len(output.extracted_fields),
                "submodel": current_submodel,
                "submodelComplete": submodel_complete,
                "allDone": all_done,
            },
        )

        self.store.save(
            SessionSnapshot(
                state=state,
                history=result.all_messages(),
                reply=output.reply,
                decision_summary=f"{len(output.extracted_fields)} fields extracted for {current_submodel}",
            )
        )

        return AgentResponse(
            thread_id=thread_id,
            reply=output.reply,
            status=state.status,
            extracted_fields=output.extracted_fields,
            missing_required=missing_required,
            missing_optional=all_optional,
            dpp_ready=dpp_ready,
            trace_events=self.store.list_events(thread_id, trace_offset),
            artifact_count=len(self.store.list_artifacts(thread_id)),
            current_submodel=current_submodel,
            submodel_status=dict(state.submodel_status),
            submodel_progress=progress,
            all_submodels_done=all_done,
        )

    async def extract_all_submodels(self, request: BulkExtractRequest) -> BulkExtractResponse:
        """Extract fields from a document for all submodels in a single LLM call."""

        if self._combined_agent is None:
            raise ValueError("OPENROUTER_API_KEY not configured.")

        thread_id = request.thread_id or f"thread-{uuid.uuid4().hex}"
        snapshot = self.store.load(thread_id)
        state = snapshot.state if snapshot is not None else MiaState(thread_id=thread_id)
        history = snapshot.history if snapshot is not None else []

        if request.company_name:
            state.company_name = request.company_name
        if request.company_website:
            state.company_website = request.company_website
        if request.document_filename:
            state.document_filename = request.document_filename

        # Build prompt with document text and known context
        parts: list[str] = []
        if state.company_name or state.company_website:
            parts.append("MANUFACTURER CONTEXT (already known — do NOT search for or ask about this):")
            if state.company_name:
                parts.append(f"- Company name: {state.company_name}")
            if state.company_website:
                parts.append(f"- Website: {state.company_website}")
            parts.append("")
        if request.document_text:
            doc_type = (request.document_type or "document").upper()
            filename = request.document_filename or "uploaded file"
            parts.append(f"DOCUMENT ({doc_type} — {filename}):")
            parts.append(request.document_text)
            parts.append("")
        parts.append("Extract all available DPP fields from the document above, sorted by submodel.")
        prompt = "\n".join(parts)

        result = await self._combined_agent.run(prompt)
        output = result.output

        # Map each submodel's extracted fields into state
        submodel_map: dict[str, list] = {
            "dpp_metadata": output.dpp_metadata,
            "digital_nameplate": output.digital_nameplate,
            "technical_data": output.technical_data,
            "carbon_footprint": output.carbon_footprint,
            "handover_documentation": output.handover_documentation,
            "maintenance_instructions": output.maintenance_instructions,
        }

        all_extracted: list = []
        missing_required: dict[str, list[str]] = {}

        for submodel_key, fields in submodel_map.items():
            if submodel_key not in state.submodel_fields:
                state.submodel_fields[submodel_key] = {}

            for field in fields:
                state.submodel_fields[submodel_key][field.idta_field] = field.value
                state.extracted_fields[field.idta_field] = field.value
            all_extracted.extend(fields)

            required = SUBMODEL_REQUIRED.get(submodel_key, ())
            sm_fields = state.submodel_fields.get(submodel_key, {})
            missing = [f for f in required if f not in sm_fields]
            missing_required[submodel_key] = missing

            if fields:
                state.submodel_status[submodel_key] = (
                    SubmodelStatus.COMPLETE if required and not missing
                    else SubmodelStatus.IN_PROGRESS
                )

        all_done = all(
            state.submodel_status.get(sm) in (SubmodelStatus.COMPLETE, SubmodelStatus.SKIPPED)
            for sm in SUBMODEL_SEQUENCE
        )
        dpp_ready = state.submodel_status.get("digital_nameplate") == SubmodelStatus.COMPLETE
        progress = _compute_progress(state)

        self.store.save(
            SessionSnapshot(
                state=state,
                history=history,
                reply=output.reply,
                decision_summary=f"Extracted {len(all_extracted)} fields across all submodels (single call)",
            )
        )

        return BulkExtractResponse(
            thread_id=thread_id,
            extracted_fields=all_extracted,
            submodel_fields=dict(state.submodel_fields),
            submodel_status=dict(state.submodel_status),
            submodel_progress=progress,
            all_submodels_done=all_done,
            dpp_ready=dpp_ready,
            missing_required=missing_required,
        )

    async def run_specialist_agent(
        self,
        agent_type: Literal["carbon_footprint", "technical_data"],
        request: SpecialistAgentRequest,
    ) -> SpecialistAgentResponse:
        """Run a web-enabled specialist agent (carbon footprint or technical data)."""

        agent = (
            self._carbon_footprint_agent
            if agent_type == "carbon_footprint"
            else self._technical_data_agent
        )
        if agent is None:
            raise ValueError("OPENROUTER_API_KEY not configured.")

        # Load session state so we can merge results back
        snapshot = self.store.load(request.thread_id)
        state = snapshot.state if snapshot is not None else MiaState(thread_id=request.thread_id)

        # Build the user prompt with all known context
        parts: list[str] = ["PRODUCT CONTEXT:"]
        if request.product_name:
            parts.append(f"- Product name: {request.product_name}")
        if request.product_url:
            parts.append(f"- Product URL: {request.product_url}")
        if request.existing_fields:
            for k, v in request.existing_fields.items():
                parts.append(f"- {k}: {v}")
        parts.append("")
        if agent_type == "carbon_footprint":
            parts.append("Use your research tools to calculate the product carbon footprint. Start by fetching the product URL if one is provided, then search for manufacturer sustainability data and material emission factors.")
        else:
            parts.append("Use your research tools to extract complete technical specifications. Start by fetching the product URL if one is provided, then search for the product datasheet.")

        prompt = "\n".join(parts)

        async with httpx.AsyncClient(
            headers={"User-Agent": "MIA-DPP/1.0 (+https://mia-dpp.vercel.app)"},
            timeout=30.0,
        ) as http_client:
            deps = WebAgentDeps(search=self._search, http=http_client, tool_trace=[])
            result = await agent.run(prompt, deps=deps)

        output = result.output
        tool_trace = deps.tool_trace

        # Merge the results back into session state
        if output.extracted_fields:
            submodel_fields = state.submodel_fields.setdefault(agent_type, {})
            for field in output.extracted_fields:
                submodel_fields[field.idta_field] = field.value
                state.extracted_fields[field.idta_field] = field.value

            # Update submodel status
            required = SUBMODEL_REQUIRED.get(agent_type, ())
            sm_fields = state.submodel_fields.get(agent_type, {})
            if required and all(f in sm_fields for f in required):
                state.submodel_status[agent_type] = SubmodelStatus.COMPLETE
            elif sm_fields:
                state.submodel_status[agent_type] = SubmodelStatus.IN_PROGRESS

        self.store.save(
            SessionSnapshot(
                state=state,
                history=snapshot.history if snapshot else [],
                reply=output.reply,
                decision_summary=f"{agent_type} specialist agent: {len(output.extracted_fields)} fields",
            )
        )

        return SpecialistAgentResponse(
            thread_id=request.thread_id,
            submodel_key=agent_type,
            reply=output.reply,
            extracted_fields=output.extracted_fields,
            methodology=output.methodology,
            confidence=output.confidence,
            data_sources=output.data_sources,
            tool_trace=tool_trace,
            calculation_inputs=output.calculation_inputs,
        )

    @staticmethod
    def _build_prompt(request: AgentRequest, state: MiaState, current_submodel: str) -> str:
        """Assemble the agent prompt from document text and session context."""

        parts: list[str] = []

        # Prepend known company context
        if state.company_name or state.company_website:
            parts.append(
                "MANUFACTURER CONTEXT (already known — do NOT search for or ask about this):"
            )
            if state.company_name:
                parts.append(f"- Company name: {state.company_name}")
            if state.company_website:
                parts.append(f"- Website: {state.company_website}")
            parts.append("")

        # Attach document text when provided
        if request.document_text:
            doc_type = (request.document_type or "document").upper()
            filename = request.document_filename or "uploaded file"
            parts.append(f"DOCUMENT ({doc_type} — {filename}):")
            parts.append(request.document_text)
            parts.append("")

        # Show fields already confirmed for this submodel in this session
        sm_fields = state.submodel_fields.get(current_submodel, {})
        if sm_fields:
            parts.append(f"FIELDS ALREADY EXTRACTED for {current_submodel}:")
            for field, value in sm_fields.items():
                parts.append(f"  {field}: {value}")
            parts.append("")

        parts.append("USER MESSAGE:")
        parts.append(request.message)

        return "\n".join(parts)


def _compute_progress(state: MiaState) -> float:
    """Return 0.0–1.0 progress across all submodels."""
    done = sum(
        1 for sm in SUBMODEL_SEQUENCE
        if state.submodel_status.get(sm) in (SubmodelStatus.COMPLETE, SubmodelStatus.SKIPPED)
    )
    return done / len(SUBMODEL_SEQUENCE)


def _label(submodel_key: str) -> str:
    from mia_dpp.agent.models import SUBMODEL_LABELS
    return SUBMODEL_LABELS.get(submodel_key, submodel_key)
