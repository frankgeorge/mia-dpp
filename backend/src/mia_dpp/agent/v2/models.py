"""Typed conversation, workflow-state, and trace contracts for Agent V2."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import AwareDatetime, Field

from mia_dpp.domain.base import WireModel
from mia_dpp.domain.discovery import CompanyCandidate, ProductCandidate
from mia_dpp.domain.mappings import SemanticReviewItem
from mia_dpp.tools.mapping.models import WebsiteIngestResponse
from mia_dpp.tools.web.models import WebExtractionResult


class AgentV2Status(StrEnum):
    RUNNING = "running"
    AWAITING_COMPANY = "awaiting_company"
    AWAITING_PRODUCT = "awaiting_product"
    AWAITING_REVIEW = "awaiting_review"
    AWAITING_INPUT = "awaiting_input"
    READY_TO_BUILD = "ready_to_build"
    COMPLETED = "completed"
    FAILED = "failed"


class TraceStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentTraceEvent(WireModel):
    """Safe, explicit activity record; never contains hidden model reasoning."""

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
    product_id: str
    candidate: ProductCandidate | None = None
    extraction: WebExtractionResult | None = None
    resolution: WebsiteIngestResponse | None = None
    pending_reviews: tuple[SemanticReviewItem, ...] = ()
    review_complete: bool = False
    aas_artifact_sha256: str | None = None


class MiaState(WireModel):
    """Durable job state, deliberately separate from model message history."""

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
    status: AgentV2Status = AgentV2Status.RUNNING
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
    """Validated final response from one autonomous decision loop run."""

    reply: str = Field(min_length=1, max_length=4000)
    status: AgentV2Status
    decision_summary: str = Field(min_length=1, max_length=500)


class AgentV2Request(WireModel):
    thread_id: str | None = Field(default=None, min_length=8, max_length=128)
    message: str = Field(min_length=1, max_length=4096)


class AgentV2Response(WireModel):
    thread_id: str
    reply: str
    status: AgentV2Status
    decision_summary: str
    company_candidates: tuple[CompanyCandidate, ...] = ()
    selected_company: CompanyCandidate | None = None
    product_candidates: tuple[ProductCandidate, ...] = ()
    selected_product_ids: tuple[str, ...] = ()
    current_product: ProductWork | None = None
    trace_events: tuple[AgentTraceEvent, ...] = ()
    mode: str = "agent_v2"
