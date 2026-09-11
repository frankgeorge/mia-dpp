"""MIA-owned contracts retained as one compatibility implementation.

No upstream framework object is allowed into these contracts. Adapters convert
Crawl4AI, BaSyx and aas-core values at the application boundary.

Feature modules expose focused ownership imports around these unchanged
Pydantic definitions. This keeps validation and wire behavior identical while
the package architecture becomes explicit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
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


class SourceType(StrEnum):
    WEBSITE = "website"
    HUMAN = "human"


class WorkflowStatus(StrEnum):
    DONE = "done"
    FAILED = "failed"


class RequirementKind(StrEnum):
    VALUE = "value"
    STRUCTURAL = "structural"


class CoverageStatus(StrEnum):
    SATISFIED = "satisfied"
    CANDIDATE = "candidate"
    AMBIGUOUS = "ambiguous"
    MISSING = "missing"


class AgentRunStatus(StrEnum):
    COMPLETED = "completed"
    AWAITING_REVIEW = "awaiting_review"
    AWAITING_INPUT = "awaiting_input"
    AWAITING_OPTIONAL_CHOICE = "awaiting_optional_choice"


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


class RawSourceArtifact(WireModel):
    """Exact source acquired by an adapter, before facts or AAS semantics exist."""

    id: str = Field(min_length=1)
    source_uri: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    acquired_at: AwareDatetime
    media_type: str = Field(min_length=1)
    source_type: SourceType
    content: str = Field(min_length=1, repr=False, exclude=True)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def hash_matches_content(self) -> RawSourceArtifact:
        if sha256(self.content.encode("utf-8")).hexdigest() != self.content_sha256:
            raise ValueError("source content does not match contentSha256")
        return self


class CandidateFact(WireModel):
    """A useful source-labelled value before semantic mapping."""

    id: str = Field(min_length=1)
    source_artifact_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    value: JsonValue
    unit: str | None = None
    source_location: SourceLocation
    extraction_method: str = Field(min_length=1)
    raw_context: str | None = None

    @model_validator(mode="after")
    def fact_has_a_value(self) -> CandidateFact:
        if self.value is None:
            raise ValueError("candidate fact must contain a value")
        return self


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
    source_label: str | None = None
    canonical_predicate: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_.-]*$",
    )
    value: JsonValue
    unit: str | None = None
    source_type: SourceType = SourceType.WEBSITE
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
    source_artifact_ids: tuple[str, ...] = ()
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


class Requirement(WireModel):
    """One actionable expectation derived from an official template element."""

    id: str = Field(pattern=r"^req-[0-9a-f]{24}$")
    template_key: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    template_release: str = Field(pattern=r"^\d+[.]\d+[.]\d+$")
    template_path: tuple[str, ...] = Field(min_length=1)
    id_short: str | None = None
    semantic_id: SemanticReference | None = None
    supplemental_semantic_ids: tuple[SemanticReference, ...] = ()
    model_type: str = Field(min_length=1)
    value_type: str | None = None
    cardinality: Cardinality | None = None
    kind: RequirementKind
    required: bool
    conditional: bool
    unit: str | None = None
    allowed_values: tuple[str, ...] = ()
    description: str | None = None
    wildcard: bool = False

    @model_validator(mode="after")
    def obligation_is_unambiguous(self) -> Requirement:
        if self.required and self.conditional:
            raise ValueError("a requirement cannot be both globally required and conditional")
        return self


class RequirementInventory(WireModel):
    """Stable requirements derived from one or more selected template releases."""

    selected_templates: tuple[TemplateRelease, ...] = Field(min_length=1)
    requirements: tuple[Requirement, ...]

    @model_validator(mode="after")
    def identities_are_unique_and_selected(self) -> RequirementInventory:
        template_keys = [item.key for item in self.selected_templates]
        if len(template_keys) != len(set(template_keys)):
            raise ValueError("selected template keys must be unique")
        requirement_ids = [item.id for item in self.requirements]
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError("requirement IDs must be unique")
        releases = {(item.key, item.release) for item in self.selected_templates}
        if any(
            (item.template_key, item.template_release) not in releases for item in self.requirements
        ):
            raise ValueError("every requirement must belong to a selected template release")
        return self


class RequirementCoverage(WireModel):
    """Deterministic coverage state for exactly one official requirement."""

    requirement_id: str = Field(pattern=r"^req-[0-9a-f]{24}$")
    status: CoverageStatus
    supporting_evidence_ids: tuple[str, ...] = ()
    candidate_evidence_ids: tuple[str, ...] = ()
    match_method: str = Field(min_length=1)
    explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def evidence_matches_status(self) -> RequirementCoverage:
        supporting = set(self.supporting_evidence_ids)
        candidates = set(self.candidate_evidence_ids)
        if len(supporting) != len(self.supporting_evidence_ids):
            raise ValueError("supporting evidence IDs must be unique")
        if len(candidates) != len(self.candidate_evidence_ids):
            raise ValueError("candidate evidence IDs must be unique")
        if supporting & candidates:
            raise ValueError("evidence cannot be both supporting and candidate")
        if self.status is CoverageStatus.SATISFIED:
            if not supporting or candidates:
                raise ValueError("satisfied coverage requires only supporting evidence")
        elif self.status in {CoverageStatus.CANDIDATE, CoverageStatus.AMBIGUOUS}:
            if supporting or not candidates:
                raise ValueError("unresolved coverage requires only candidate evidence")
        elif supporting or candidates:
            raise ValueError("missing coverage cannot reference evidence")
        return self


class CoverageStatistics(WireModel):
    selected_templates: int = Field(ge=1)
    requirements: int = Field(ge=0)
    required_requirements: int = Field(ge=0)
    required_satisfied: int = Field(ge=0)
    required_candidate: int = Field(ge=0)
    required_ambiguous: int = Field(ge=0)
    required_missing: int = Field(ge=0)
    optional_requirements: int = Field(ge=0)
    optional_satisfied: int = Field(ge=0)
    optional_candidate: int = Field(ge=0)
    optional_ambiguous: int = Field(ge=0)
    optional_missing: int = Field(ge=0)
    evidence_records: int = Field(ge=0)
    evidence_used: int = Field(ge=0)
    unmatched_evidence: int = Field(ge=0)

    @model_validator(mode="after")
    def subtotals_match(self) -> CoverageStatistics:
        required = (
            self.required_satisfied
            + self.required_candidate
            + self.required_ambiguous
            + self.required_missing
        )
        optional = (
            self.optional_satisfied
            + self.optional_candidate
            + self.optional_ambiguous
            + self.optional_missing
        )
        if required != self.required_requirements:
            raise ValueError("required coverage statistics do not add up")
        if optional != self.optional_requirements:
            raise ValueError("optional coverage statistics do not add up")
        if required + optional != self.requirements:
            raise ValueError("coverage statistics do not include every requirement")
        if self.evidence_used + self.unmatched_evidence != self.evidence_records:
            raise ValueError("coverage statistics do not include every evidence record")
        return self


class CoverageReport(WireModel):
    """Bidirectional accounting between retained evidence and target requirements."""

    inventory: RequirementInventory
    coverage: tuple[RequirementCoverage, ...]
    analyzed_evidence_ids: tuple[str, ...]
    unmatched_evidence_ids: tuple[str, ...]
    statistics: CoverageStatistics

    @model_validator(mode="after")
    def requirements_and_evidence_are_accounted_for(self) -> CoverageReport:
        expected_requirements = [item.id for item in self.inventory.requirements]
        actual_requirements = [item.requirement_id for item in self.coverage]
        if actual_requirements != expected_requirements:
            raise ValueError("coverage must follow and include every inventory requirement")
        if len(self.analyzed_evidence_ids) != len(set(self.analyzed_evidence_ids)):
            raise ValueError("analyzed evidence IDs must be unique")
        if len(self.unmatched_evidence_ids) != len(set(self.unmatched_evidence_ids)):
            raise ValueError("unmatched evidence IDs must be unique")
        used = {
            evidence_id
            for item in self.coverage
            for evidence_id in (*item.supporting_evidence_ids, *item.candidate_evidence_ids)
        }
        analyzed = set(self.analyzed_evidence_ids)
        unmatched = set(self.unmatched_evidence_ids)
        if used & unmatched or used | unmatched != analyzed:
            raise ValueError("every analyzed evidence record must be used or unmatched")
        if self.statistics.requirements != len(self.coverage):
            raise ValueError("requirement statistics differ from coverage")
        if self.statistics.evidence_records != len(analyzed):
            raise ValueError("evidence statistics differ from analyzed evidence")
        if self.statistics.evidence_used != len(used):
            raise ValueError("used evidence statistics differ from coverage")
        if self.statistics.unmatched_evidence != len(unmatched):
            raise ValueError("unmatched evidence statistics differ from coverage")
        return self


class SourceFactStatistics(WireModel):
    """Evidence outcomes, counted independently from template requirements."""

    total_discovered: int = Field(ge=0)
    automatically_resolved: int = Field(ge=0)
    accepted_after_review: int = Field(ge=0)
    pending_review: int = Field(ge=0)
    unresolved: int = Field(ge=0)
    rejected_proposals: int = Field(ge=0)


class FixedTemplateCompletion(WireModel):
    """Completion of real, scalar fields in one official template."""

    template_key: str
    template_name: str
    mandatory_total: int = Field(ge=0)
    mandatory_filled: int = Field(ge=0)
    mandatory_missing: int = Field(ge=0)
    optional_total: int = Field(ge=0)
    optional_filled: int = Field(ge=0)
    optional_missing: int = Field(ge=0)


class TechnicalDataCompletion(WireModel):
    """Source-led technical facts; wildcard slots are never missing fields."""

    discovered: int = Field(ge=0)
    resolved: int = Field(ge=0)
    unresolved: int = Field(ge=0)


class CompletionSummary(WireModel):
    """Human-oriented accounting across source, fixed targets, and extensions."""

    source: SourceFactStatistics
    fixed_templates: tuple[FixedTemplateCompletion, ...]
    technical_data: TechnicalDataCompletion


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


class MappingResult(WireModel):
    """Downstream mapping outcome; unmatched evidence remains in the knowledge package."""

    mapped: tuple[ProposedFieldMapping, ...] = ()
    ambiguous: tuple[ProposedFieldMapping, ...] = ()
    unmatched_evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def evidence_outcomes_are_unique(self) -> MappingResult:
        identifiers = [item.evidence_id for item in (*self.mapped, *self.ambiguous)]
        identifiers.extend(self.unmatched_evidence_ids)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("an evidence record must have exactly one mapping outcome")
        return self


class WorkflowEvent(WireModel):
    """Framework-neutral record of one execution stage that actually ran."""

    id: str = Field(min_length=1)
    stage: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    status: WorkflowStatus
    started_at: AwareDatetime
    completed_at: AwareDatetime
    input_count: int = Field(ge=0)
    output_count: int = Field(ge=0)
    summary: str = Field(min_length=1)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def completion_follows_start(self) -> WorkflowEvent:
        if self.completed_at < self.started_at:
            raise ValueError("workflow event completedAt cannot precede startedAt")
        return self


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
    evidence: tuple[EvidenceRecord, ...] = ()


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


class WebsiteIngestRequest(WireModel):
    url: str = Field(min_length=10, max_length=2048, pattern=r"^https?://")
    graph: tuple[GraphEntry, ...] = ()
    template_keys: tuple[str, ...] = ("digital_nameplate", "technical_data")

    @model_validator(mode="after")
    def selected_template_keys_are_unique(self) -> WebsiteIngestRequest:
        if not self.template_keys:
            raise ValueError("at least one template key must be selected")
        if len(self.template_keys) != len(set(self.template_keys)):
            raise ValueError("selected template keys must be unique")
        return self


class WebsiteIngestResponse(WireModel):
    reply: str
    source_url: str
    proposal: MappingProposal
    evidence: tuple[EvidenceRecord, ...]
    knowledge_package: ProductKnowledgePackage
    mapping_result: MappingResult
    coverage_report: CoverageReport
    completion_summary: CompletionSummary
    workflow_events: tuple[WorkflowEvent, ...]
    mode: Literal["website"] = "website"
    nameplate_elements: tuple[NameplateElement, ...]

    @model_validator(mode="after")
    def legacy_evidence_matches_knowledge_package(self) -> WebsiteIngestResponse:
        if self.evidence != self.knowledge_package.evidence:
            raise ValueError("evidence must match knowledgePackage.evidence")
        proposal = (*self.mapping_result.mapped, *self.mapping_result.ambiguous)
        if self.proposal.mappings != proposal:
            raise ValueError("proposal mappings must match mappingResult")
        if self.coverage_report.analyzed_evidence_ids != tuple(item.id for item in self.evidence):
            raise ValueError("coverageReport must analyze every evidence record in order")
        return self


class ConversationDecision(WireModel):
    """Typed result of the conversational intake model."""

    intent: Literal["chat", "ingest_website"]
    reply: str = Field(min_length=1)
    url: str | None = None

    @model_validator(mode="after")
    def website_intent_has_url(self) -> ConversationDecision:
        if self.intent == "ingest_website" and not self.url:
            raise ValueError("website ingestion intent requires a URL")
        if self.intent == "chat" and self.url is not None:
            raise ValueError("chat intent cannot include a URL")
        return self


class SemanticMatchDecision(WireModel):
    """Provider-neutral semantic suggestion constrained to existing domain IDs."""

    evidence_id: str = Field(min_length=1)
    requirement_id: str = Field(pattern=r"^req-[0-9a-f]{24}$")
    reasoning: str = Field(min_length=1, max_length=600)


class SemanticReviewItem(WireModel):
    """One semantic proposal that must be accepted or rejected by a person."""

    id: str = Field(pattern=r"^review-[0-9a-f]{24}$")
    requirement_id: str = Field(pattern=r"^req-[0-9a-f]{24}$")
    mapping: ProposedFieldMapping


class AgentMessageRequest(WireModel):
    thread_id: str | None = Field(default=None, min_length=8, max_length=128)
    message: str = Field(min_length=1, max_length=4096)
    graph: tuple[GraphEntry, ...] = ()


class AgentReviewDecision(WireModel):
    review_id: str = Field(pattern=r"^review-[0-9a-f]{24}$")
    decision: Literal["approve", "correct", "reject"]
    corrected_requirement_id: str | None = Field(
        default=None,
        pattern=r"^req-[0-9a-f]{24}$",
    )
    corrected_value: str | None = Field(default=None, min_length=1, max_length=4096)
    comment: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def correction_has_a_change(self) -> AgentReviewDecision:
        if self.decision == "correct" and not (
            self.corrected_requirement_id or self.corrected_value
        ):
            raise ValueError("a correction must change the target or value")
        if self.decision != "correct" and (
            self.corrected_requirement_id is not None or self.corrected_value is not None
        ):
            raise ValueError("only a correction may include a corrected target or value")
        return self


class AgentReviewRequest(WireModel):
    thread_id: str = Field(min_length=8, max_length=128)
    decisions: tuple[AgentReviewDecision, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def review_ids_are_unique(self) -> AgentReviewRequest:
        identifiers = [item.review_id for item in self.decisions]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("review decisions must be unique")
        return self


class AgentResponse(WireModel):
    """One resumable MIA graph result returned to the workspace."""

    thread_id: str
    reply: str
    status: AgentRunStatus
    mode: Literal["agent", "configuration_required"] = "agent"
    website_result: WebsiteIngestResponse | None = None
    review_items: tuple[SemanticReviewItem, ...] = ()


class DppBuildRequest(WireModel):
    product_name: str
    mappings: tuple[FieldMapping, ...]
    evidence: tuple[EvidenceRecord, ...] = ()


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
