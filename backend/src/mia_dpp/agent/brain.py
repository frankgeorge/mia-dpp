"""The single autonomous PydanticAI decision loop for MIA agent."""

from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic_ai import Agent
from pydantic_ai.capabilities import Capability
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model

from mia_dpp.aas.build import DeterministicDppPipeline
from mia_dpp.agent.dependencies import MiaDependencies
from mia_dpp.agent.models import (
    AgentRunOutput,
    AgentStatus,
    MiaState,
    TraceStatus,
)
from mia_dpp.agent.prompts import AGENT_INSTRUCTIONS, DPP_CREATION_SKILL
from mia_dpp.agent.tools import AGENT_TOOLS
from mia_dpp.tools.company.tool import CompanyDiscoveryTool
from mia_dpp.tools.mapping.resolver import ProductResolver
from mia_dpp.tools.mapping.review import MappingReviewService
from mia_dpp.tools.products.research import ProductResearchTool
from mia_dpp.tools.products.tool import ProductDiscoveryTool
from mia_dpp.tools.web.tool import WebExtractionTool
from mia_dpp.workspace.store import WorkspaceStore


class AutonomousAgent:
    """Run MIA's single model-led plan/act/observe loop.

    API routes call this runtime for conversation turns and human reviews. It
    supplies trusted state, history, and tools to PydanticAI, then persists the
    updated thread after each turn.
    """

    def __init__(
        self,
        *,
        model: Model | None,
        workspace: WorkspaceStore,
        company_tool: CompanyDiscoveryTool,
        product_tool: ProductDiscoveryTool,
        product_research_tool: ProductResearchTool,
        web_tool: WebExtractionTool,
        mapping_tool: ProductResolver,
        mapping_review: MappingReviewService,
        dpp_pipeline: DeterministicDppPipeline,
    ) -> None:
        """Configure one PydanticAI agent with MIA's trusted capabilities.

        ``bootstrap`` supplies the model, stores, tools, mapping services, and
        AAS pipeline. If no model is configured, the runtime remains available
        and returns an explicit configuration-required response.
        """

        self._workspace = workspace
        self._company_tool = company_tool
        self._product_tool = product_tool
        self._product_research_tool = product_research_tool
        self._web_tool = web_tool
        self._mapping_tool = mapping_tool
        self._mapping_review = mapping_review
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
                name="mia-agent",
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

    async def run(
        self,
        message: str,
        state: MiaState,
        history: Sequence[ModelMessage],
    ) -> tuple[AgentRunOutput, list[ModelMessage], int]:
        """Let PydanticAI choose and repeat tools for one lifecycle turn.

        LangGraph supplies checkpointed state/history and persists the result.
        This method owns autonomous decisions but not workflow lifetime.
        """
        trace_offset = len(state.trace)
        if self._agent is None:
            state.status = AgentStatus.AWAITING_INPUT
            state.add_event(
                "run.configuration_required",
                "MIA agent requires OPENROUTER_API_KEY.",
            )
            return (
                AgentRunOutput(
                    reply="Configure OPENROUTER_API_KEY to use the autonomous MIA agent.",
                    status=AgentStatus.AWAITING_INPUT,
                    decision_summary=(
                        "No model call was attempted because the server is unconfigured."
                    ),
                ),
                list(history),
                trace_offset,
            )

        dependencies = MiaDependencies(
            state=state,
            company_tool=self._company_tool,
            product_tool=self._product_tool,
            product_research_tool=self._product_research_tool,
            web_tool=self._web_tool,
            mapping_tool=self._mapping_tool,
            mapping_review=self._mapping_review,
            dpp_pipeline=self._dpp_pipeline,
            workspace=self._workspace,
        )
        state.add_event(
            "run.started",
            "MIA started an autonomous decision loop.",
            status=TraceStatus.STARTED,
            input_summary=message[:200],
        )
        result = await self._agent.run(
            self._prompt_with_state(message, state),
            deps=dependencies,
            message_history=history,
            conversation_id=state.thread_id,
        )
        output = result.output
        if state.status is AgentStatus.RUNNING:
            state.status = output.status
        state.add_event(
            "run.completed",
            output.decision_summary,
            metadata={
                "requestCount": result.usage.requests,
                "inputTokens": result.usage.input_tokens,
                "outputTokens": result.usage.output_tokens,
            },
        )
        return output, result.all_messages(), trace_offset

    @staticmethod
    def _prompt_with_state(message: str, state: MiaState) -> str:
        """Attach a compact trusted job summary to the new user message.

        Large evidence remains in workflow state; the model receives only the
        identifiers and counts needed to choose its next tool safely.
        """

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
                    "sourceCount": len(value.extractions),
                    "sourceCandidates": [
                        {
                            "id": item.id,
                            "url": item.url,
                            "authoritative": item.authoritative_domain,
                        }
                        for item in value.source_candidates
                    ],
                    "hasEvidence": bool(value.extractions),
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
