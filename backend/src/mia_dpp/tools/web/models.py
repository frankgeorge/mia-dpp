"""Operational contracts used by the web extraction tool."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol

from pydantic import Field

from mia_dpp.domain.base import WireModel
from mia_dpp.errors import ExtractionError


class ExtractionDependencyError(ExtractionError):
    """A selected web implementation is not installed."""


class ProductUrlRejectedError(ExtractionError):
    """A URL violates the configured admission policy."""


class PageLoadError(ExtractionError):
    """The page loader could not return usable HTML."""


@dataclass(frozen=True)
class SourceLink:
    url: str
    text: str = ""
    title: str = ""


class DownloadedSource(WireModel):
    """One explicitly downloaded technical source file."""

    final_url: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=1)
    content: bytes


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

    async def discover(self, url: str) -> tuple[SourceLink, ...]: ...
