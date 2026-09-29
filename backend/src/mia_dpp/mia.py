"""MIA composition root — document-first DPP extraction agent."""

from __future__ import annotations

import uuid

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
    ExtractionOutput,
    MiaState,
    TraceStatus,
)
from mia_dpp.agent.prompts import AGENT_INSTRUCTIONS
from mia_dpp.config import Settings
from mia_dpp.store import SessionSnapshot, Store

# IDTA 02006 Digital Nameplate required fields (matches template id_short + address fields)
REQUIRED_FIELDS: tuple[str, ...] = (
    "ManufacturerName",
    "ManufacturerProductDesignation",
    "OrderCodeOfManufacturer",
    "URIOfTheProduct",
    "Street",
    "ZipCode",
    "CityTown",
    "NationalCode",
)

# Optional fields to track
OPTIONAL_FIELDS: tuple[str, ...] = (
    "ProductArticleNumberOfManufacturer",
    "SerialNumber",
    "YearOfConstruction",
    "HardwareVersion",
    "SoftwareVersion",
    "CountryOfOrigin",
    "Phone",
    "Fax",
)


class Mia:
    """Compose MIA and run document-extraction DPP agent sessions.

    The agent reads document text supplied by the frontend, extracts IDTA 02006
    Digital Nameplate fields using the LLM, and returns a structured response.
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

        self._agent: Agent[None, ExtractionOutput] | None = None
        if agent_model is not None:
            self._agent = Agent(
                agent_model,
                name="mia-extractor",
                output_type=ExtractionOutput,
                instructions=AGENT_INSTRUCTIONS,
                retries=1,
                model_settings=ModelSettings(
                    temperature=0,
                    max_tokens=2048,
                ),
            )

    @property
    def configured(self) -> bool:
        """Return whether an autonomous model is available."""

        return self._agent is not None

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

        if self._agent is None:
            self.store.add_event(
                thread_id,
                "run.configuration_required",
                "OPENROUTER_API_KEY not configured.",
            )
            return AgentResponse(
                thread_id=thread_id,
                reply="Configure OPENROUTER_API_KEY to use the MIA agent.",
                status=AgentStatus.FAILED,
                trace_events=self.store.list_events(thread_id, trace_offset),
            )

        self.store.add_event(
            thread_id,
            "run.started",
            "MIA started document extraction.",
            status=TraceStatus.STARTED,
            input_summary=(request.document_filename or request.message)[:200],
        )

        prompt = self._build_prompt(request, state)
        result = await self._agent.run(prompt, message_history=history)
        output = result.output

        # Merge extracted fields into persistent session state
        for field in output.extracted_fields:
            state.extracted_fields[field.idta_field] = field.value

        # Compute missing fields against the full session state
        missing_required = [f for f in REQUIRED_FIELDS if f not in state.extracted_fields]
        missing_optional = [f for f in OPTIONAL_FIELDS if f not in state.extracted_fields]
        dpp_ready = len(missing_required) == 0

        state.status = AgentStatus.COMPLETED if dpp_ready else AgentStatus.NEEDS_INPUT

        self.store.add_event(
            thread_id,
            "run.completed",
            (
                f"Extracted {len(output.extracted_fields)} field(s). "
                f"Missing required: {len(missing_required)}."
            ),
            status=TraceStatus.COMPLETED,
            metadata={
                "extracted": len(output.extracted_fields),
                "missingRequired": len(missing_required),
                "dppReady": dpp_ready,
            },
        )

        self.store.save(
            SessionSnapshot(
                state=state,
                history=result.all_messages(),
                reply=output.reply,
                decision_summary=f"{len(output.extracted_fields)} fields extracted",
            )
        )

        return AgentResponse(
            thread_id=thread_id,
            reply=output.reply,
            status=state.status,
            extracted_fields=output.extracted_fields,
            missing_required=missing_required,
            missing_optional=missing_optional,
            dpp_ready=dpp_ready,
            trace_events=self.store.list_events(thread_id, trace_offset),
            artifact_count=len(self.store.list_artifacts(thread_id)),
        )

    @staticmethod
    def _build_prompt(request: AgentRequest, state: MiaState) -> str:
        """Assemble the agent prompt from document text and session context."""

        parts: list[str] = []

        # Prepend known company context so agent never needs to look it up
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

        # Show fields already confirmed in this session
        if state.extracted_fields:
            parts.append("FIELDS ALREADY EXTRACTED in this session:")
            for field, value in state.extracted_fields.items():
                parts.append(f"  {field}: {value}")
            parts.append("")

        parts.append("USER MESSAGE:")
        parts.append(request.message)

        return "\n".join(parts)
