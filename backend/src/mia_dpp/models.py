"""MIA-owned domain contracts and JSON API models.

No upstream framework object is allowed into these contracts. Adapters convert
Crawl4AI, BaSyx and aas-core values at the application boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)


def to_camel(name: str) -> str:
    """Convert Python names to the camelCase expected by the frontend."""

    first, *rest = name.split("_")
    return first + "".join(part.capitalize() for part in rest)


def utc_now() -> datetime:
    """Return an aware UTC time."""

    return datetime.now(UTC)


class WireModel(BaseModel):
    """Strict model with stable camelCase JSON names."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )


class MappingStatus(StrEnum):
    AUTO = "auto"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"


class EvidenceStatus(StrEnum):
    OBSERVED = "observed"
    INFERRED = "inferred"
    VERIFIED = "verified"
    CONFLICTING = "conflicting"
    REJECTED = "rejected"


class ExtractionSource(StrEnum):
    CSS = "css"
    XPATH = "xpath"
    JSON_LD = "json_ld"
    META = "meta"


class Cardinality(StrEnum):
    ONE = "One"
    ZERO_TO_ONE = "ZeroToOne"
    ONE_TO_MANY = "OneToMany"
    ZERO_TO_MANY = "ZeroToMany"

    @property
    def minimum(self) -> int:
        return 1 if self in {Cardinality.ONE, Cardinality.ONE_TO_MANY} else 0

    @property
    def maximum(self) -> int | None:
        return 1 if self in {Cardinality.ONE, Cardinality.ZERO_TO_ONE} else None


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ValidationCategory(StrEnum):
    METAMODEL = "metamodel"
    TEMPLATE = "template"
    POLICY = "policy"


class ReferenceKey(WireModel):
    type: str = Field(min_length=1)
    value: str = Field(min_length=1)


class SemanticReference(WireModel):
    type: str = Field(min_length=1)
    keys: tuple[ReferenceKey, ...] = Field(min_length=1)

    @property
    def primary_value(self) -> str:
        return self.keys[0].value


class SourceLocation(WireModel):
    """Location of one fact in its original source."""

    page: int | None = Field(default=None, ge=1)
    selector: str | None = None
    json_pointer: str | None = None
    excerpt: str | None = None
    table: str | None = None
    cell: str | None = None


class ConfidenceFactor(WireModel):
    """One visible contribution to a deterministic confidence score."""

    code: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)
    awarded: float = Field(ge=0.0, le=1.0)
    maximum: float = Field(gt=0.0, le=1.0)
    explanation: str = Field(min_length=1)
    uncertainty: str | None = None

    @model_validator(mode="after")
    def awarded_does_not_exceed_maximum(self) -> ConfidenceFactor:
        if self.awarded > self.maximum:
            raise ValueError("awarded confidence points cannot exceed maximum")
        return self


class ConfidenceAssessment(WireModel):
    """Explainable score whose arithmetic can be reproduced by the user."""

    score: float = Field(ge=0.0, le=1.0)
    factors: tuple[ConfidenceFactor, ...] = Field(min_length=1)
    remaining_uncertainty: tuple[str, ...] = ()

    @model_validator(mode="after")
    def score_matches_factors(self) -> ConfidenceAssessment:
        expected = round(sum(factor.awarded for factor in self.factors), 4)
        if abs(self.score - expected) > 0.0001:
            raise ValueError("confidence score must equal awarded factor points")
        maximum = round(sum(factor.maximum for factor in self.factors), 4)
        if abs(maximum - 1.0) > 0.0001:
            raise ValueError("confidence factor maxima must add up to 1.0")
        expected_uncertainty = tuple(
            factor.uncertainty
            for factor in self.factors
            if factor.awarded < factor.maximum and factor.uncertainty
        )
        if self.remaining_uncertainty != expected_uncertainty:
            raise ValueError("remaining uncertainty must be derived from incomplete factors")
        return self


class EvidenceRecord(WireModel):
    """One traceable fact; the compiler never accepts a bare value."""

    id: str = Field(min_length=1)
    predicate: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    value: JsonValue
    unit: str | None = None
    source_uri: str = Field(min_length=1)
    source_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_location: SourceLocation
    extraction_method: str = Field(min_length=1)
    extractor_name: str = Field(min_length=1)
    extractor_version: str = Field(min_length=1)
    status: EvidenceStatus
    acquired_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def accepted_evidence_has_a_value(self) -> EvidenceRecord:
        if (
            self.status
            in {
                EvidenceStatus.OBSERVED,
                EvidenceStatus.INFERRED,
                EvidenceStatus.VERIFIED,
            }
            and self.value is None
        ):
            raise ValueError("usable evidence must contain a value")
        return self


class ExtractionRule(WireModel):
    predicate: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    source: ExtractionSource
    selector: str = Field(min_length=1)
    attribute: str | None = None
    many: bool = False
    required: bool = False
    unit: str | None = None


class SiteAdapterSpec(WireModel):
    """Reviewed, declarative instructions for repeatable website extraction."""

    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    site_origin: str = Field(pattern=r"^https?://")
    allowed_hosts: tuple[str, ...] = Field(min_length=1)
    product_url_patterns: tuple[str, ...] = Field(min_length=1)
    field_rules: tuple[ExtractionRule, ...] = Field(min_length=1)
    approved: bool = False

    @model_validator(mode="after")
    def rules_are_unique(self) -> SiteAdapterSpec:
        predicates = [rule.predicate for rule in self.field_rules]
        if len(predicates) != len(set(predicates)):
            raise ValueError("site adapter predicates must be unique")
        return self


class ProductKnowledgePackage(WireModel):
    """Framework-neutral evidence collected for one product."""

    product_id: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    evidence: tuple[EvidenceRecord, ...]

    @model_validator(mode="after")
    def evidence_ids_are_unique(self) -> ProductKnowledgePackage:
        identifiers = [item.id for item in self.evidence]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("evidence IDs must be unique")
        return self


class DocumentReference(WireModel):
    """Content-addressed local document discovered from product evidence."""

    uri: str = Field(min_length=1)
    local_path: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: str = Field(min_length=1)
    acquired_at: AwareDatetime = Field(default_factory=utc_now)


class TemplateRelease(WireModel):
    """Exact official template artifact selected for a build."""

    key: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    family: str = Field(min_length=1)
    release: str = Field(pattern=r"^\d+[.]\d+[.]\d+$")
    repository_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_path: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metamodel_version: str = Field(min_length=1)


class TemplateElement(WireModel):
    """Normalized recursive view of an official submodel template element."""

    source_pointer: str = Field(min_length=1)
    path: tuple[str, ...] = Field(min_length=1)
    id_short: str | None = None
    model_type: str = Field(min_length=1)
    semantic_id: SemanticReference | None = None
    supplemental_semantic_ids: tuple[SemanticReference, ...] = ()
    cardinality: Cardinality | None = None
    value_type: str | None = None
    type_value_list_element: str | None = None
    value_type_list_element: str | None = None
    semantic_id_list_element: SemanticReference | None = None
    order_relevant: bool | None = None
    unit: str | None = None
    allowed_values: tuple[str, ...] = ()
    wildcard: bool = False
    description: str | None = None
    children: tuple[TemplateElement, ...] = ()


class SubmodelTemplate(WireModel):
    release: TemplateRelease
    id: str = Field(min_length=1)
    id_short: str = Field(min_length=1)
    template_id: str | None = None
    administration_version: str | None = None
    administration_revision: str | None = None
    semantic_id: SemanticReference
    elements: tuple[TemplateElement, ...]


class TargetProfile(WireModel):
    """Versioned choice of one official target for deterministic compilation."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    template: TemplateRelease
    aas_metamodel_version: Literal["3.0"] = "3.0"
    language: str = "en"


class MappingTarget(WireModel):
    template_key: str
    template_release: str
    template_path: tuple[str, ...] = Field(min_length=1)
    instance_path: tuple[str, ...] = Field(min_length=1)
    id_short: str = Field(min_length=1)
    semantic_id: SemanticReference
    model_type: str
    value_type: str | None = None
    wildcard: bool = False


class MappingDraft(WireModel):
    """One evidence value proposed for an official template target."""

    evidence_id: str = Field(min_length=1)
    source_field: str
    source_value: str
    target_element: str
    semantic_id: str
    target: MappingTarget
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_assessment: ConfidenceAssessment
    reasoning: str
    from_graph: bool = False

    @model_validator(mode="after")
    def legacy_fields_match_typed_target(self) -> MappingDraft:
        if self.target_element != self.target.id_short:
            raise ValueError("targetElement must match target.idShort")
        if self.semantic_id != self.target.semantic_id.primary_value:
            raise ValueError("semanticId must match the authoritative target")
        if abs(self.confidence - self.confidence_assessment.score) > 0.0001:
            raise ValueError("confidence must match confidenceAssessment.score")
        return self


class FieldMapping(MappingDraft):
    id: str
    status: MappingStatus


class ProposedFieldMapping(MappingDraft):
    status: MappingStatus


class ApprovedMapping(WireModel):
    evidence_id: str
    target: MappingTarget
    confidence_assessment: ConfidenceAssessment


class MappingSpecification(WireModel):
    """Frozen deterministic instructions produced by the review action."""

    id: str
    target_profile: TargetProfile
    mappings: tuple[ApprovedMapping, ...]
    approved_at: AwareDatetime

    @model_validator(mode="after")
    def instance_targets_are_unique(self) -> MappingSpecification:
        paths = [item.target.instance_path for item in self.mappings]
        if len(paths) != len(set(paths)):
            raise ValueError("mapping instance paths must be unique")
        return self


class Gap(WireModel):
    template_path: tuple[str, ...]
    message: str
    severity: Severity


class GapReport(WireModel):
    template_key: str
    gaps: tuple[Gap, ...] = ()
    blocks_deployment: bool

    @model_validator(mode="after")
    def blocking_flag_matches_gaps(self) -> GapReport:
        expected = any(gap.severity is Severity.ERROR for gap in self.gaps)
        if self.blocks_deployment != expected:
            raise ValueError("blocksDeployment must match error-severity gaps")
        return self


class ValidationFinding(WireModel):
    category: ValidationCategory
    code: str
    message: str
    severity: Severity
    instance_path: tuple[str, ...] = ()
    template_path: tuple[str, ...] = ()
    expected: str | None = None
    actual: str | None = None


class ValidationReport(WireModel):
    valid: bool
    template_key: str
    template_release: str
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validator_versions: dict[str, str]
    findings: tuple[ValidationFinding, ...] = ()

    @model_validator(mode="after")
    def valid_matches_findings(self) -> ValidationReport:
        expected = not any(item.severity is Severity.ERROR for item in self.findings)
        if self.valid != expected:
            raise ValueError("valid must be false exactly when an error finding exists")
        return self


class AasArtifact(WireModel):
    environment: dict[str, Any]
    submodel: dict[str, Any]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    compiler_name: str
    compiler_version: str


class DeploymentResult(WireModel):
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    repository_url: str = Field(min_length=1)
    shell_ids: tuple[str, ...]
    submodel_ids: tuple[str, ...]
    status: Literal["deployed"] = "deployed"


class DppPackage(WireModel):
    product_name: str
    generated_at: str
    submodel: dict[str, Any]
    environment: dict[str, Any]
    passport_id: str
    artifact_sha256: str
    target_profile: TargetProfile
    gap_report: GapReport
    validation_report: ValidationReport
    deployable: bool


class DemoProposal(WireModel):
    product_name: str
    evidence: tuple[EvidenceRecord, ...]
    mappings: tuple[MappingDraft, ...]


class MappingProposal(WireModel):
    product_name: str
    mappings: tuple[ProposedFieldMapping, ...]


class GraphEntry(WireModel):
    source_field: str
    target_element: str
    semantic_id: str
    verified_at: str
    corrections: int


class ChatMessage(WireModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(WireModel):
    messages: tuple[ChatMessage, ...] = ()
    graph: tuple[GraphEntry, ...] = ()


class NameplateElement(WireModel):
    name: str
    path: tuple[str, ...]
    semantic_id: str
    hint: str
    required: bool
    model_type: str
    value_type: str | None = None
    target: MappingTarget


class ChatResponse(WireModel):
    reply: str
    proposal: MappingProposal | None = None
    generate: bool = False
    mode: str
    nameplate_elements: tuple[NameplateElement, ...]


class DppBuildRequest(WireModel):
    product_name: str
    mappings: tuple[FieldMapping, ...]


class TemplateSummary(WireModel):
    key: str
    family: str
    release: str
    id_short: str
    template_id: str | None
    semantic_id: str
    source_sha256: str
    element_count: int


class HealthResponse(WireModel):
    status: Literal["ok", "not_ready"]
    version: str
    standards_ready: bool
    standards_commit: str
