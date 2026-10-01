"""Typed conversation and state contracts for MIA document-extraction agent."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, Field

from mia_dpp.domain.base import WireModel

SUBMODEL_SEQUENCE: tuple[str, ...] = (
    "dpp_metadata",
    "digital_nameplate",
    "technical_data",
    "carbon_footprint",
    "handover_documentation",
    "maintenance_instructions",
)

SUBMODEL_LABELS: dict[str, str] = {
    "dpp_metadata": "DPP Metadata",
    "digital_nameplate": "Digital Nameplate",
    "technical_data": "Technical Data",
    "carbon_footprint": "Carbon Footprint",
    "handover_documentation": "Handover Documentation",
    "maintenance_instructions": "Maintenance Instructions",
}

# Minimum required fields per submodel (frontend mirrors these)
SUBMODEL_REQUIRED: dict[str, tuple[str, ...]] = {
    "dpp_metadata": ("uniqueProductIdentifier", "economicOperatorId"),
    "digital_nameplate": (
        "ManufacturerName",
        "ManufacturerProductDesignation",
        "OrderCodeOfManufacturer",
        "URIOfTheProduct",
    ),
    "technical_data": ("GeneralInformation",),
    "carbon_footprint": (
        "PCFCO2eq",
        "ReferenceValueForCalculation",
        "QuantityOfMeasureForCalculation",
    ),
    "handover_documentation": ("Title", "OrganizationOfficialName"),
    "maintenance_instructions": ("MaintenanceFreeAsset",),
}


class AgentStatus(StrEnum):
    """Current state of an MIA extraction session."""

    RUNNING = "running"
    NEEDS_INPUT = "needs_input"
    COMPLETED = "completed"
    FAILED = "failed"


class SubmodelStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    SKIPPED = "skipped"


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
    """One field extracted from a document and mapped to an IDTA id_short name."""

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
    # Flat dict of all extracted fields (backward compat)
    extracted_fields: dict[str, str] = Field(default_factory=dict)
    # Per-submodel fields
    submodel_fields: dict[str, dict[str, str]] = Field(default_factory=dict)
    # Per-submodel status
    submodel_status: dict[str, str] = Field(
        default_factory=lambda: {sm: SubmodelStatus.PENDING for sm in SUBMODEL_SEQUENCE}
    )
    current_submodel: str = SUBMODEL_SEQUENCE[0]
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
    current_submodel: str = Field(default=SUBMODEL_SEQUENCE[0], max_length=64)
    action: Literal["skip"] | None = None
    known_fields: dict[str, str] | None = Field(default=None)


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
    # Multi-submodel progress
    current_submodel: str = SUBMODEL_SEQUENCE[0]
    submodel_status: dict[str, str] = Field(default_factory=dict)
    submodel_progress: float = 0.0
    all_submodels_done: bool = False


class CombinedExtractionOutput(WireModel):
    """Structured output for single-call multi-submodel extraction."""

    reply: str = Field(min_length=1, max_length=4000)
    dpp_metadata: list[ExtractedField] = Field(default_factory=list)
    digital_nameplate: list[ExtractedField] = Field(default_factory=list)
    technical_data: list[ExtractedField] = Field(default_factory=list)
    carbon_footprint: list[ExtractedField] = Field(default_factory=list)
    handover_documentation: list[ExtractedField] = Field(default_factory=list)
    maintenance_instructions: list[ExtractedField] = Field(default_factory=list)


class BulkExtractRequest(WireModel):
    """HTTP-safe input for bulk multi-submodel document extraction."""

    thread_id: str | None = Field(default=None, min_length=8, max_length=128)
    document_text: str | None = Field(default=None, max_length=200_000)
    document_filename: str | None = Field(default=None, max_length=256)
    document_type: str | None = Field(default=None, max_length=32)
    company_name: str | None = Field(default=None, max_length=256)
    company_website: str | None = Field(default=None, max_length=512)
    known_fields: dict[str, str] | None = Field(default=None)


class BulkExtractResponse(WireModel):
    """Aggregated extraction result across all submodels."""

    thread_id: str
    extracted_fields: list[ExtractedField] = Field(default_factory=list)
    submodel_fields: dict[str, dict[str, str]] = Field(default_factory=dict)
    submodel_status: dict[str, str] = Field(default_factory=dict)
    submodel_progress: float = 0.0
    all_submodels_done: bool = False
    dpp_ready: bool = False
    missing_required: dict[str, list[str]] = Field(default_factory=dict)
