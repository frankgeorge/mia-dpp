"""LangGraph orchestration for MIA's conversational ingestion MVP."""

from __future__ import annotations

import hashlib
import json
import operator
import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from mia_dpp.completion import build_completion_summary
from mia_dpp.confidence import (
    MatchQuality,
    ValueFormatQuality,
    assess_mapping_confidence,
)
from mia_dpp.coverage import CoverageAnalyzer
from mia_dpp.idta import mapping_target
from mia_dpp.models import (
    AgentMessageRequest,
    AgentResponse,
    AgentReviewDecision,
    AgentReviewRequest,
    AgentRunStatus,
    ChatMessage,
    EvidenceRecord,
    EvidenceStatus,
    GraphEntry,
    MappingResult,
    MappingStatus,
    ProposedFieldMapping,
    SemanticReviewItem,
    SourceLocation,
    SourceType,
    WebsiteIngestRequest,
    WebsiteIngestResponse,
)
from mia_dpp.reasoning import ReasoningService
from mia_dpp.templates import OfficialTemplateRepository
from mia_dpp.website import WebsiteIngestionService
from mia_dpp.workflow import completed_event

_URL = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)


class AgentState(TypedDict, total=False):
    """LangGraph-owned state; API/domain objects cross the boundary as JSON."""

    messages: Annotated[list[dict[str, str]], operator.add]
    user_message: str
    route: Literal["chat", "website"]
    reply: str
    configured: bool
    graph_history: list[dict[str, Any]]
    website_url: str
    website_result: dict[str, Any] | None
    review_items: list[dict[str, Any]]
    status: Literal["completed", "awaiting_review"]


class MiaAgentWorkflow:
    """Persist and resume the conversation, tools, and human semantic review."""

    def __init__(
        self,
        repository: OfficialTemplateRepository,
        website_ingestion: WebsiteIngestionService,
        reasoning: ReasoningService,
    ) -> None:
        self._repository = repository
        self._website_ingestion = website_ingestion
        self._reasoning = reasoning
        self._coverage_analyzer = CoverageAnalyzer()
        self._pending_chat: dict[str, list[ChatMessage]] = {}
        builder = StateGraph(AgentState)
        builder.add_node("intake", self._intake)
        builder.add_node("website_ingestion", self._ingest_website)
        builder.add_node("semantic_resolution", self._resolve_semantics)
        builder.add_node("human_review", self._human_review)
        builder.add_edge(START, "intake")
        builder.add_conditional_edges(
            "intake",
            self._after_intake,
            {"website": "website_ingestion", "done": END},
        )
        builder.add_edge("website_ingestion", "semantic_resolution")
        builder.add_conditional_edges(
            "semantic_resolution",
            self._after_semantics,
            {"review": "human_review", "done": END},
        )
        builder.add_edge("human_review", END)
        self._graph = builder.compile(checkpointer=InMemorySaver())

    async def message(self, request: AgentMessageRequest) -> AgentResponse:
        thread_id = request.thread_id or f"thread-{uuid.uuid4().hex}"
        if request.thread_id:
            snapshot = await self._graph.aget_state(self._config(thread_id))
            if snapshot.next and snapshot.values.get("review_items"):
                return await self._message_during_review(thread_id, request, snapshot.values)
        state: AgentState = {
            "messages": [{"role": "user", "content": request.message}],
            "user_message": request.message,
            "graph_history": [item.model_dump(mode="json") for item in request.graph],
            "configured": self._reasoning.configured,
            "website_result": None,
            "review_items": [],
            "status": "completed",
        }
        result = await self._graph.ainvoke(state, self._config(thread_id))
        return self._response(thread_id, result)

    async def _message_during_review(
        self,
        thread_id: str,
        request: AgentMessageRequest,
        state: dict[str, Any],
    ) -> AgentResponse:
        """Keep conversation available without consuming the review interrupt."""

        stored = self._pending_chat.setdefault(thread_id, [])
        history = tuple(
            [ChatMessage.model_validate(item) for item in state.get("messages", [])]
            + stored
            + [ChatMessage(role="user", content=request.message)]
        )
        decision = await self._reasoning.converse(history)
        stored.extend(
            [
                ChatMessage(role="user", content=request.message),
                ChatMessage(role="assistant", content=decision.reply),
            ]
        )
        response_state = dict(state)
        response_state["reply"] = decision.reply
        response_state["status"] = "awaiting_review"
        return self._response(thread_id, response_state)

    async def review(self, request: AgentReviewRequest) -> AgentResponse:
        command: Command[Any] = Command(resume=request.model_dump(mode="json"))
        result = await self._graph.ainvoke(
            command,
            self._config(request.thread_id),
        )
        self._pending_chat.pop(request.thread_id, None)
        return self._response(request.thread_id, result)

    async def _intake(self, state: AgentState) -> AgentState:
        message = state["user_message"]
        match = _URL.search(message)
        if match:
            url = match.group(0).rstrip(".,;:!?)']")
            return {
                "route": "website",
                "website_url": url,
                "reply": "I found a product URL and will build its evidence ledger now.",
            }

        history = tuple(ChatMessage.model_validate(item) for item in state.get("messages", []))
        decision = await self._reasoning.converse(history)
        if decision.intent == "ingest_website" and decision.url:
            return {
                "route": "website",
                "website_url": decision.url,
                "reply": decision.reply,
            }
        return {
            "route": "chat",
            "reply": decision.reply,
            "messages": [{"role": "assistant", "content": decision.reply}],
            "status": "completed",
        }

    async def _after_intake(self, state: AgentState) -> Literal["website", "done"]:
        return "website" if state["route"] == "website" else "done"

    async def _ingest_website(self, state: AgentState) -> AgentState:
        history = tuple(GraphEntry.model_validate(item) for item in state.get("graph_history", []))
        result = await self._website_ingestion.ingest(
            WebsiteIngestRequest(url=state["website_url"], graph=history)
        )
        return {"website_result": result.model_dump(mode="json")}

    async def _resolve_semantics(self, state: AgentState) -> AgentState:
        website = WebsiteIngestResponse.model_validate(state["website_result"])
        started_at = datetime.now(UTC)
        decisions = await self._reasoning.propose_semantic_matches(
            website.knowledge_package,
            website.coverage_report,
        )
        already_used = {
            item.evidence_id
            for item in (*website.mapping_result.mapped, *website.mapping_result.ambiguous)
        }
        existing_paths = {
            item.target.instance_path
            for item in (*website.mapping_result.mapped, *website.mapping_result.ambiguous)
        }
        requirements = {item.id: item for item in website.coverage_report.inventory.requirements}
        evidence = {item.id: item for item in website.evidence}
        review_items: list[SemanticReviewItem] = []
        by_target = {
            (item.template_key, item.template_release, item.template_path): item
            for item in requirements.values()
        }
        for proposal in (*website.mapping_result.mapped, *website.mapping_result.ambiguous):
            if proposal.status is not MappingStatus.REVIEW:
                continue
            requirement = by_target.get(
                (
                    proposal.target.template_key,
                    proposal.target.template_release,
                    proposal.target.template_path,
                )
            )
            if requirement is None:
                continue
            identity = f"{requirement.id}\0{proposal.evidence_id}"
            review_items.append(
                SemanticReviewItem(
                    id="review-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
                    requirement_id=requirement.id,
                    mapping=proposal,
                )
            )
        for decision in decisions:
            requirement = requirements.get(decision.requirement_id)
            record = evidence.get(decision.evidence_id)
            if requirement is None or record is None or record.id in already_used:
                continue
            template = self._repository.load(requirement.template_key)
            target = mapping_target(template, requirement.template_path)
            if target.instance_path in existing_paths:
                continue
            assessment = assess_mapping_confidence(
                source_label=MatchQuality.WEAK,
                value_format=ValueFormatQuality.PLAUSIBLE,
                semantic_match=MatchQuality.STRONG,
                destination_candidates=1,
            )
            mapping = ProposedFieldMapping(
                evidence_id=record.id,
                source_field=record.source_label or record.predicate,
                source_value=self._display_value(record.value, record.unit),
                target_element=target.id_short,
                semantic_id=target.semantic_id.primary_value,
                target=target,
                confidence=assessment.score,
                confidence_assessment=assessment,
                reasoning=(
                    "Semantic proposal from the configured model; human approval is required. "
                    + decision.reasoning
                ),
                status=MappingStatus.REVIEW,
            )
            identity = f"{decision.requirement_id}\0{decision.evidence_id}"
            review_items.append(
                SemanticReviewItem(
                    id="review-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
                    requirement_id=decision.requirement_id,
                    mapping=mapping,
                )
            )
            already_used.add(record.id)
            existing_paths.add(target.instance_path)

        semantic_event = completed_event(
            stage="reasoning.semantic",
            started_at=started_at,
            input_count=website.coverage_report.statistics.unmatched_evidence,
            output_count=len(review_items),
            summary=(
                f"Produced {len(review_items)} constrained semantic proposal"
                f"{'s' if len(review_items) != 1 else ''} for human review."
            ),
            metadata={
                "configured": self._reasoning.configured,
                "authoritative": False,
            },
        )
        website = website.model_copy(
            update={"workflow_events": (*website.workflow_events, semantic_event)}
        )
        if review_items:
            reply = (
                f"I retained {len(website.evidence)} source facts and found "
                f"{len(review_items)} additional semantic proposal"
                f"{'s' if len(review_items) != 1 else ''}. Please review each before continuing."
            )
            return {
                "website_result": website.model_dump(mode="json"),
                "review_items": [item.model_dump(mode="json") for item in review_items],
                "reply": reply,
                "status": "awaiting_review",
            }

        if self._reasoning.configured:
            reply = (
                f"I retained {len(website.evidence)} source facts. The semantic model found no "
                "additional mapping that was safe enough to propose; unresolved evidence remains "
                "visible for later research or clarification."
            )
        else:
            reply = (
                f"I retained {len(website.evidence)} source facts and completed deterministic "
                "coverage. Configure OPENROUTER_API_KEY to reason over unresolved mappings."
            )
        return {
            "website_result": website.model_dump(mode="json"),
            "reply": reply,
            "messages": [{"role": "assistant", "content": reply}],
            "status": "completed",
        }

    async def _after_semantics(self, state: AgentState) -> Literal["review", "done"]:
        return "review" if state.get("review_items") else "done"

    async def _human_review(self, state: AgentState) -> AgentState:
        items = tuple(SemanticReviewItem.model_validate(item) for item in state["review_items"])
        submission = AgentReviewRequest.model_validate(
            interrupt(
                {
                    "type": "semantic_mapping_review",
                    "reviewItems": [item.model_dump(mode="json") for item in items],
                    "allowedDecisions": ["approve", "correct", "reject"],
                }
            )
        )
        if submission.thread_id == "":
            raise ValueError("thread ID is required")
        decisions = {item.review_id: item for item in submission.decisions}
        expected = {item.id for item in items}
        if set(decisions) != expected:
            raise ValueError("a decision is required for every semantic proposal")
        website = WebsiteIngestResponse.model_validate(state["website_result"])
        reviewed = [
            self._apply_review_decision(item, decisions[item.id], website) for item in items
        ]
        website = self._reconcile_review(website, reviewed)
        approved = sum(item.mapping.status is MappingStatus.APPROVED for item in reviewed)
        reply = (
            f"Review saved: {approved} semantic mapping"
            f"{'s' if approved != 1 else ''} approved and {len(reviewed) - approved} rejected. "
            "Approved mappings can now participate in deterministic compilation."
        )
        return {
            "website_result": website.model_dump(mode="json"),
            "review_items": [item.model_dump(mode="json") for item in reviewed],
            "reply": reply,
            "messages": [{"role": "assistant", "content": reply}],
            "status": "completed",
        }

    def _apply_review_decision(
        self,
        item: SemanticReviewItem,
        decision: AgentReviewDecision,
        website: WebsiteIngestResponse,
    ) -> SemanticReviewItem:
        if decision.decision == "reject":
            return item.model_copy(
                update={
                    "mapping": item.mapping.model_copy(update={"status": MappingStatus.REJECTED})
                }
            )
        if decision.decision == "approve":
            return item.model_copy(
                update={
                    "mapping": item.mapping.model_copy(update={"status": MappingStatus.APPROVED})
                }
            )

        requirement_id = decision.corrected_requirement_id or item.requirement_id
        requirements = {
            requirement.id: requirement
            for requirement in website.coverage_report.inventory.requirements
        }
        requirement = requirements.get(requirement_id)
        if requirement is None or requirement.semantic_id is None or requirement.wildcard:
            raise ValueError("corrected target must be a fixed official requirement")
        target = mapping_target(
            self._repository.load(requirement.template_key),
            requirement.template_path,
        )
        mapping = item.mapping
        if decision.corrected_value is not None:
            record = self._human_correction_evidence(
                mapping,
                decision.corrected_value,
            )
            package = website.knowledge_package.model_copy(
                update={"evidence": (*website.knowledge_package.evidence, record)}
            )
            website.knowledge_package = package
            website.evidence = package.evidence
            mapping = mapping.model_copy(
                update={
                    "evidence_id": record.id,
                    "source_value": decision.corrected_value,
                }
            )
        mapping = mapping.model_copy(
            update={
                "target_element": target.id_short,
                "semantic_id": target.semantic_id.primary_value,
                "target": target,
                "status": MappingStatus.APPROVED,
                "reasoning": (
                    "Corrected and approved by the human reviewer. "
                    + (decision.comment or "The official target was validated by MIA.")
                ),
            }
        )
        return SemanticReviewItem(id=item.id, requirement_id=requirement_id, mapping=mapping)

    def _human_correction_evidence(
        self,
        mapping: ProposedFieldMapping,
        value: str,
    ) -> EvidenceRecord:
        acquired_at = datetime.now(UTC)
        identity = f"{mapping.evidence_id}\0{value}\0{acquired_at.isoformat()}"
        return EvidenceRecord(
            id="ev-human-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
            predicate="human.correction",
            source_label=mapping.source_field,
            value=value,
            source_type=SourceType.HUMAN,
            source_uri="mia://conversation/review",
            source_content_sha256=hashlib.sha256(value.encode()).hexdigest(),
            source_location=SourceLocation(excerpt=value),
            extraction_method="human_review_correction",
            extractor_name="mia-human-review",
            extractor_version="1",
            status=EvidenceStatus.VERIFIED,
            acquired_at=acquired_at,
        )

    def _reconcile_review(
        self,
        website: WebsiteIngestResponse,
        reviewed: list[SemanticReviewItem],
    ) -> WebsiteIngestResponse:
        base = [
            item
            for item in (*website.mapping_result.mapped, *website.mapping_result.ambiguous)
            if item.status is MappingStatus.AUTO
        ]
        approved = [
            item.mapping for item in reviewed if item.mapping.status is MappingStatus.APPROVED
        ]
        mapped_ids = {item.evidence_id for item in (*base, *approved)}
        unmatched = tuple(item.id for item in website.evidence if item.id not in mapped_ids)
        result = MappingResult(mapped=(*base, *approved), unmatched_evidence_ids=unmatched)
        coverage = self._coverage_analyzer.analyze(
            website.knowledge_package,
            website.coverage_report.inventory,
            mapping_result=result,
        )
        return website.model_copy(
            update={
                "proposal": website.proposal.model_copy(update={"mappings": result.mapped}),
                "mapping_result": result,
                "coverage_report": coverage,
                "completion_summary": build_completion_summary(coverage, result),
            }
        )

    def _response(self, thread_id: str, state: dict[str, Any]) -> AgentResponse:
        website = state.get("website_result")
        items = state.get("review_items", [])
        status = AgentRunStatus(state.get("status", "completed"))
        return AgentResponse(
            thread_id=thread_id,
            reply=state.get("reply", "MIA is ready."),
            status=status,
            mode="agent" if state.get("configured") else "configuration_required",
            website_result=(
                WebsiteIngestResponse.model_validate(website) if website is not None else None
            ),
            review_items=tuple(SemanticReviewItem.model_validate(item) for item in items),
        )

    @staticmethod
    def _display_value(value: object, unit: str | None) -> str:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return f"{text} {unit}" if unit and not str(text).endswith(unit) else str(text)

    @staticmethod
    def _config(thread_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": thread_id}}
