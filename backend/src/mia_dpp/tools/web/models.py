"""Operational contracts used by the web extraction tool."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Protocol

from pydantic import AwareDatetime, Field, JsonValue, model_validator

from mia_dpp.domain.base import WireModel
from mia_dpp.domain.evidence import ProductKnowledgePackage, SourceLocation, SourceType
from mia_dpp.errors import ExtractionError


class ExtractionDependencyError(ExtractionError):
    """A selected web implementation is not installed."""


class ProductUrlRejectedError(ExtractionError):
    """A URL violates the configured admission policy."""


class RequiredEvidenceMissingError(ExtractionError):
    """A required adapter rule did not produce a value."""


class PageLoadError(ExtractionError):
    """The page loader could not return usable HTML."""


class ExtractionSource(StrEnum):
    CSS = "css"
    XPATH = "xpath"
    JSON_LD = "json_ld"
    META = "meta"


class RawSourceArtifact(WireModel):
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


class ExtractionRule(WireModel):
    predicate: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    source: ExtractionSource
    selector: str = Field(min_length=1)
    attribute: str | None = None
    many: bool = False
    required: bool = False
    unit: str | None = None


class SiteAdapterSpec(WireModel):
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


@dataclass(frozen=True)
class RenderedPage:
    url: str
    html: str
    acquired_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.url:
            raise ValueError("rendered page URL must not be empty")
        if self.acquired_at.tzinfo is None or self.acquired_at.utcoffset() is None:
            raise ValueError("rendered page acquisition time must include a timezone")

    @property
    def content_sha256(self) -> str:
        return sha256(self.html.encode("utf-8")).hexdigest()


class PageLoader(Protocol):
    async def load(self, url: str) -> RenderedPage: ...


class WebExtractionResult(WireModel):
    source_url: str
    product_name: str
    knowledge_package: ProductKnowledgePackage
