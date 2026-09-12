"""The single autonomous PydanticAI decision loop for Agent V2."""

from __future__ import annotations

import json
import uuid

from pydantic_ai import Agent
from pydantic_ai.capabilities import Capability
from pydantic_ai.models import Model

from mia_dpp.aas.build import DeterministicDppPipeline
from mia_dpp.agent.v2.dependencies import MiaDependencies
from mia_dpp.agent.v2.models import (
    AgentRunOutput,
    AgentV2Request,
    AgentV2Response,
    AgentV2Status,
    MiaState,
    TraceStatus,
)
from mia_dpp.agent.v2.prompts import AGENT_INSTRUCTIONS, DPP_CREATION_SKILL
from mia_dpp.agent.v2.store import ThreadStore
from mia_dpp.agent.v2.tools import AGENT_TOOLS
from mia_dpp.tools.company.tool import CompanyDiscoveryTool
from mia_dpp.tools.mapping.resolver import ProductResolver
from mia_dpp.tools.products.tool import ProductDiscoveryTool
from mia_dpp.tools.web.tool import WebExtractionTool


class MiaAgentV2:
    """Own one model-led plan/act/observe loop and trusted thread persistence."""

    def __init__(
        self,
        *,
        model: Model | None,
        store: ThreadStore,
        company_tool: CompanyDiscoveryTool,
        product_tool: ProductDiscoveryTool,
        web_tool: WebExtractionTool,
        mapping_tool: ProductResolver,
        dpp_pipeline: DeterministicDppPipeline,
    ) -> None:
        self._store = store
        self._company_tool = company_tool
        self._product_tool = product_tool
        self._web_tool = web_tool
        self._mapping_tool = mapping_tool
        self._dpp_pipeline = dpp_pipeline
        self._configured = model is not None
        self._agent: Agent[MiaDependencies, AgentRunOutput] | None = None
        if model is not None:
            skill = Capability[MiaDependencies](
                id="dpp-creation",
                description="How MIA approaches evidence-backed DPP and AAS creation.",
                instructions=DPP_CREATION_SKILL,
            )
            agent = Agent[MiaDependencies, AgentRunOutput](
                model,
                name="mia-agent-v2",
                deps_type=MiaDependencies,
                output_type=AgentRunOutput,
                instructions=AGENT_INSTRUCTIONS,
                tools=AGENT_TOOLS,
                capabilities=[skill],
                retries=2,
            )

            self._agent = agent

    @property
    def configured(self) -> bool:
        return self._configured

    async def message(self, request: AgentV2Request) -> AgentV2Response:
        thread_id = request.thread_id or f"thread-{uuid.uuid4().hex}"
        snapshot = await self._store.load(thread_id)
        if snapshot is None:
            state = MiaState(thread_id=thread_id, user_goal=request.message)
            history = []
        else:
            state = snapshot.state
            history = snapshot.messages
            if not state.user_goal:
                state.user_goal = request.message

        trace_offset = len(state.trace)
        if self._agent is None:
            state.status = AgentV2Status.AWAITING_INPUT
            state.add_event(
                "run.configuration_required",
                "Agent V2 requires OPENROUTER_API_KEY.",
            )
            await self._store.save(state, history)
            return self._response(
                state,
                reply="Configure OPENROUTER_API_KEY to use the autonomous MIA agent.",
                decision_summary="No model call was attempted because the server is unconfigured.",
                trace_offset=trace_offset,
            )

        dependencies = MiaDependencies(
            state=state,
            company_tool=self._company_tool,
            product_tool=self._product_tool,
            web_tool=self._web_tool,
            mapping_tool=self._mapping_tool,
            dpp_pipeline=self._dpp_pipeline,
        )
        state.add_event(
            "run.started",
            "MIA started an autonomous decision loop.",
            status=TraceStatus.STARTED,
            input_summary=request.message[:200],
        )
        result = await self._agent.run(
            self._prompt_with_state(request.message, state),
            deps=dependencies,
            message_history=history,
            conversation_id=thread_id,
        )
        output = result.output
        if state.status is AgentV2Status.RUNNING:
            state.status = output.status
        state.add_event(
            "run.completed",
            output.decision_summary,
            metadata={"requestCount": result.usage.requests},
        )
        await self._store.save(state, result.all_messages())
        return self._response(
            state,
            reply=output.reply,
            decision_summary=output.decision_summary,
            trace_offset=trace_offset,
        )

    @staticmethod
    def _prompt_with_state(message: str, state: MiaState) -> str:
        compact = {
            "threadId": state.thread_id,
            "goal": state.user_goal,
            "selectedCompany": (
                state.selected_company.model_dump(mode="json") if state.selected_company else None
            ),
            "companyCandidates": [
                {"id": item.id, "name": item.name, "domain": item.domain}
                for item in state.company_candidates
            ],
            "productCandidates": [
                {"id": item.id, "name": item.name, "url": item.official_url}
                for item in state.product_candidates
            ],
            "selectedProductIds": list(state.selected_product_ids),
            "products": {
                key: {
                    "hasEvidence": value.extraction is not None,
                    "hasMapping": value.resolution is not None,
                    "pendingReviews": len(value.pending_reviews),
                    "hasArtifact": value.aas_artifact_sha256 is not None,
                }
                for key, value in state.products.items()
            },
            "status": state.status,
        }
        return (
            message
            + "\n\nTrusted current MIA job state (server supplied):\n"
            + json.dumps(compact, ensure_ascii=False)
        )

    @staticmethod
    def _response(
        state: MiaState,
        *,
        reply: str,
        decision_summary: str,
        trace_offset: int,
    ) -> AgentV2Response:
        current = state.products.get(state.current_product_id) if state.current_product_id else None
        return AgentV2Response(
            thread_id=state.thread_id,
            reply=reply,
            status=state.status,
            decision_summary=decision_summary,
            company_candidates=state.company_candidates,
            selected_company=state.selected_company,
            product_candidates=state.product_candidates,
            selected_product_ids=state.selected_product_ids,
            current_product=current,
            trace_events=state.trace[trace_offset:],
        )
