"""Source facts, provenance, and product knowledge."""

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256

from pydantic import AwareDatetime, Field, JsonValue, model_validator

from mia_dpp.domain.base import WireModel, utc_now


class EvidenceStatus(StrEnum):
    OBSERVED = "observed"
    INFERRED = "inferred"
    VERIFIED = "verified"
    CONFLICTING = "conflicting"
    REJECTED = "rejected"


class SourceType(StrEnum):
    WEBSITE = "website"
    HUMAN = "human"


class ExtractionSource(StrEnum):
    CSS = "css"
    XPATH = "xpath"
    JSON_LD = "json_ld"
    META = "meta"


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
