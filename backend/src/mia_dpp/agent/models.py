"""Typed conversation and state contracts for MIA document-extraction agent."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, Field

from mia_dpp.domain.base import WireModel


class AgentStatus(StrEnum):
    """Current state of an MIA extraction session."""

    RUNNING = "running"
    NEEDS_INPUT = "needs_input"
    COMPLETED = "completed"
    FAILED = "failed"


class TraceStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentTraceEvent(WireModel):
    """Safe activity record shown by the frontend activity page."""

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


class ExtractedField(WireModel):
    """One field extracted from a document and mapped to an IDTA 02006 name."""

    idta_field: str
    value: str
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    source_excerpt: str = ""


class ExtractionOutput(WireModel):
    """Structured output returned by the PydanticAI extraction agent."""

    reply: str = Field(min_length=1, max_length=4000)
    extracted_fields: list[ExtractedField] = Field(default_factory=list)
    missing_required: list[str] = Field(default_factory=list)
    missing_optional: list[str] = Field(default_factory=list)


class MiaState(WireModel):
    """Trusted workflow state for one DPP extraction session."""

    thread_id: str
    company_name: str | None = None
    company_website: str | None = None
    document_filename: str | None = None
    extracted_fields: dict[str, str] = Field(default_factory=dict)
    status: AgentStatus = AgentStatus.RUNNING


class AgentRequest(WireModel):
    """HTTP-safe input for one agent turn."""

    thread_id: str | None = Field(default=None, min_length=8, max_length=128)
    message: str = Field(min_length=1, max_length=4096)
    document_text: str | None = Field(default=None, max_length=200_000)
    document_filename: str | None = Field(default=None, max_length=256)
    document_type: str | None = Field(default=None, max_length=32)
    company_name: str | None = Field(default=None, max_length=256)
    company_website: str | None = Field(default=None, max_length=512)


class AgentResponse(WireModel):
    """Structured MIA agent result consumed by the workspace."""

    thread_id: str
    reply: str
    status: AgentStatus
    extracted_fields: list[ExtractedField] = Field(default_factory=list)
    missing_required: list[str] = Field(default_factory=list)
    missing_optional: list[str] = Field(default_factory=list)
    dpp_ready: bool = False
    trace_events: tuple[AgentTraceEvent, ...] = ()
    artifact_count: int = 0
