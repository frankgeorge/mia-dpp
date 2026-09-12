"""Mapping, confidence, coverage, and semantic-review concepts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, Field, model_validator

from mia_dpp.domain.base import WireModel
from mia_dpp.domain.evidence import EvidenceRecord
from mia_dpp.domain.targets import RequirementInventory, SemanticReference, TargetProfile


class MappingStatus(StrEnum):
    AUTO = "auto"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"


class MappingOrigin(StrEnum):
    DETERMINISTIC = "deterministic"
    SEMANTIC_AGENT = "semantic_agent"
    HUMAN = "human"


class CoverageStatus(StrEnum):
    SATISFIED = "satisfied"
    CANDIDATE = "candidate"
    AMBIGUOUS = "ambiguous"
    MISSING = "missing"


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
    mapping_origin: MappingOrigin = MappingOrigin.DETERMINISTIC
    human_reviewed: bool = False

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


class TextMappingProposal(WireModel):
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


class NameplateElement(WireModel):
    name: str
    path: tuple[str, ...]
    semantic_id: str
    hint: str
    required: bool
    model_type: str
    value_type: str | None = None
    target: MappingTarget


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
