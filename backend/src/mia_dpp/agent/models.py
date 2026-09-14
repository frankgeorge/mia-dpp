"""Typed conversation, workflow-state, and trace contracts for MIA agent."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, Field

from mia_dpp.domain.base import WireModel
from mia_dpp.domain.discovery import CompanyCandidate, ProductCandidate, ProductSourceCandidate
from mia_dpp.domain.evidence import ProductKnowledgePackage
from mia_dpp.domain.mappings import SemanticReviewItem
from mia_dpp.tools.mapping.models import ProductResolution
from mia_dpp.tools.web.models import WebExtractionResult


class AgentStatus(StrEnum):
    """Current point at which an MIA agent job can continue or must pause."""

    RUNNING = "running"
    AWAITING_COMPANY = "awaiting_company"
    AWAITING_PRODUCT = "awaiting_product"
    AWAITING_REVIEW = "awaiting_review"
    AWAITING_INPUT = "awaiting_input"
    AWAITING_OPTIONAL_CHOICE = "awaiting_optional_choice"
    READY_TO_BUILD = "ready_to_build"
    COMPLETED = "completed"
    FAILED = "failed"


class TraceStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class ProductStatus(StrEnum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    AWAITING_REVIEW = "awaiting_review"
    READY_TO_BUILD = "ready_to_build"
    COMPLETED = "completed"
    FAILED = "failed"


class HumanRequestKind(StrEnum):
    MAPPING_REVIEW = "mapping_review"
    REQUIREMENT_VALUE = "requirement_value"


class HumanRequest(WireModel):
    """Trusted pause request created by the agent but answerable only through the API."""

    kind: HumanRequestKind
    product_id: str
    summary: str
    requirement_id: str | None = None


class AgentTraceEvent(WireModel):
    """Safe activity record shown by the frontend.

    Tools append these events to ``MiaState`` when work starts, completes, or
    fails. They summarize observable actions and never contain hidden reasoning.
    """

    id: str
    thread_id: str
    event_type: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    status: TraceStatus
    timestamp: AwareDatetime
    summary: str
    tool_name: str | None = None
    product_id: str | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    source_ids: tuple[str, ...] = ()
    duration_ms: int | None = Field(default=None, ge=0)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ProductWork(WireModel):
    """All trusted working data accumulated for one selected product.

    Agent tools update its sources, evidence resolution, pending reviews, and
    artifact identity as the autonomous loop progresses.
    """

    product_id: str
    status: ProductStatus = ProductStatus.QUEUED
    candidate: ProductCandidate | None = None
    source_candidates: tuple[ProductSourceCandidate, ...] = ()
    extractions: tuple[WebExtractionResult, ...] = ()
    resolution: ProductResolution | None = None
    pending_reviews: tuple[SemanticReviewItem, ...] = ()
    review_complete: bool = False
    aas_artifact_sha256: str | None = None
    artifact_ids: tuple[str, ...] = ()

    def combined_extraction(self) -> WebExtractionResult | None:
        """Combine repeated source acquisitions before deterministic mapping.

        ``map_product_evidence`` calls this after one or more page extractions.
        It preserves source identities while deduplicating evidence by ID.
        """

        if not self.extractions:
            return None
        primary = self.extractions[0]
        evidence = []
        evidence_ids: set[str] = set()
        artifact_ids: list[str] = []
        for extraction in self.extractions:
            for artifact_id in extraction.knowledge_package.source_artifact_ids:
                if artifact_id not in artifact_ids:
                    artifact_ids.append(artifact_id)
            for record in extraction.knowledge_package.evidence:
                if record.id not in evidence_ids:
                    evidence_ids.add(record.id)
                    evidence.append(record)
        package = ProductKnowledgePackage(
            product_id=self.product_id,
            product_name=primary.product_name,
            source_artifact_ids=tuple(artifact_ids),
            evidence=tuple(evidence),
        )
        return WebExtractionResult(
            source_url=primary.source_url,
            product_name=primary.product_name,
            knowledge_package=package,
        )


class MiaState(WireModel):
    """Trusted workflow state for one DPP job/thread.

    Tools mutate this state as companies, products, evidence, reviews, and
    artifacts are discovered. PydanticAI message history is stored separately:
    it records the conversation, while this model records the job's facts.
    """

    thread_id: str
    user_goal: str = ""
    company_candidates: tuple[CompanyCandidate, ...] = ()
    selected_company: CompanyCandidate | None = None
    product_candidates: tuple[ProductCandidate, ...] = ()
    selected_product_ids: tuple[str, ...] = ()
    current_product_id: str | None = None
    product_queue: tuple[str, ...] = ()
    products: dict[str, ProductWork] = Field(default_factory=dict)
    target_submodels: tuple[str, ...] = ("digital_nameplate", "technical_data")
    status: AgentStatus = AgentStatus.RUNNING
    pending_human_request: HumanRequest | None = None
    trace: tuple[AgentTraceEvent, ...] = ()

    def add_event(
        self,
        event_type: str,
        summary: str,
        *,
        status: TraceStatus = TraceStatus.COMPLETED,
        tool_name: str | None = None,
        product_id: str | None = None,
        input_summary: str | None = None,
        output_summary: str | None = None,
        source_ids: tuple[str, ...] = (),
        duration_ms: int | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> AgentTraceEvent:
        """Append one safe execution event and return it to the caller.

        Agent tools use this to make state changes visible to the activity UI.
        The runtime later returns only events added during the current turn.
        """

        now = datetime.now(UTC)
        seed = f"{self.thread_id}\0{event_type}\0{now.isoformat()}\0{len(self.trace)}"
        event = AgentTraceEvent(
            id="trace-" + hashlib.sha256(seed.encode()).hexdigest()[:24],
            thread_id=self.thread_id,
            event_type=event_type,
            status=status,
            timestamp=now,
            summary=summary,
            tool_name=tool_name,
            product_id=product_id,
            input_summary=input_summary,
            output_summary=output_summary,
            source_ids=source_ids,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )
        self.trace = (*self.trace, event)
        return event


class AgentRunOutput(WireModel):
    """Validated model output returned after one autonomous tool loop.

    PydanticAI produces this after tool calls stop; the runtime combines it with
    trusted state rather than asking the model to recreate workflow data.
    """

    reply: str = Field(min_length=1, max_length=4000)
    status: AgentStatus
    decision_summary: str = Field(min_length=1, max_length=500)


class AgentRequest(WireModel):
    """HTTP-safe input containing only a thread ID and the new user message."""

    thread_id: str | None = Field(default=None, min_length=8, max_length=128)
    message: str = Field(min_length=1, max_length=4096)


class AgentReviewDecision(WireModel):
    """One explicit approve, correct, or reject decision from the human UI."""

    review_id: str
    decision: Literal["approve", "correct", "reject"]
    corrected_requirement_id: str | None = None
    corrected_value: str | None = Field(default=None, max_length=4096)
    comment: str | None = Field(default=None, max_length=1000)


class AgentReviewRequest(WireModel):
    """Batch of review decisions for one product in one trusted thread."""

    thread_id: str = Field(min_length=8, max_length=128)
    product_id: str
    decisions: tuple[AgentReviewDecision, ...] = Field(min_length=1)


class AgentValueRequest(WireModel):
    """Trusted human value submitted while LangGraph is paused for a requirement."""

    thread_id: str = Field(min_length=8, max_length=128)
    product_id: str
    requirement_id: str
    value: str = Field(min_length=1, max_length=4096)


class AgentResponse(WireModel):
    """Structured MIA agent result consumed by the workspace.

    It combines conversational text with trusted candidate, product, review,
    and trace state so the frontend never needs to infer workflow from prose.
    """

    thread_id: str
    reply: str
    status: AgentStatus
    decision_summary: str
    company_candidates: tuple[CompanyCandidate, ...] = ()
    selected_company: CompanyCandidate | None = None
    product_candidates: tuple[ProductCandidate, ...] = ()
    selected_product_ids: tuple[str, ...] = ()
    current_product: ProductWork | None = None
    pending_human_request: HumanRequest | None = None
    trace_events: tuple[AgentTraceEvent, ...] = ()
    artifact_count: int = 0
    mode: str = "agent"
