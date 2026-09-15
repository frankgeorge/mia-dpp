"""Typed conversation, workflow-state, and trace contracts for MIA agent."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, Field, computed_field

from mia_dpp.domain.base import WireModel
from mia_dpp.domain.discovery import CompanyCandidate, ProductCandidate, ProductSourceCandidate
from mia_dpp.domain.evidence import EvidenceRecord, ProductKnowledgePackage
from mia_dpp.domain.mappings import (
    CoverageReport,
    MappingResult,
    SemanticReviewItem,
)
from mia_dpp.domain.targets import TemplateIndex
from mia_dpp.tools.mapping.coverage import coverage


class AgentStatus(StrEnum):
    """Current point at which an MIA agent job can continue or must pause."""

    RUNNING = "running"
    AWAITING_COMPANY = "awaiting_company"
    AWAITING_PRODUCT = "awaiting_product"
    AWAITING_REVIEW = "awaiting_review"
    AWAITING_INPUT = "awaiting_input"
    AWAITING_OPTIONAL_CHOICE = "awaiting_optional_choice"
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
    product_name: str | None = None
    source_urls: tuple[str, ...] = ()
    source_artifact_ids: tuple[str, ...] = ()
    evidence: tuple[EvidenceRecord, ...] = ()
    mapping_result: MappingResult | None = None
    template_index: TemplateIndex | None = None
    pending_reviews: tuple[SemanticReviewItem, ...] = ()
    aas_artifact_sha256: str | None = None
    artifact_ids: tuple[str, ...] = ()

    def knowledge_package(self) -> ProductKnowledgePackage | None:
        """Build the source-neutral mapping input from canonical product evidence."""

        if not self.evidence:
            return None
        return ProductKnowledgePackage(
            product_id=self.product_id,
            product_name=self.product_name
            or (self.candidate.name if self.candidate else self.product_id),
            source_artifact_ids=self.source_artifact_ids,
            evidence=self.evidence,
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def coverage_report(self) -> CoverageReport | None:
        """Derive coverage from the current evidence, mappings, and template index."""

        package = self.knowledge_package()
        if package is None or self.mapping_result is None or self.template_index is None:
            return None
        return coverage(package, self.template_index, mapping_result=self.mapping_result)


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
    """Trusted human value submitted for a deferred requirement request."""

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
