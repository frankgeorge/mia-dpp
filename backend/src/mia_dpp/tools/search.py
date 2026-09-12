"""Provider-neutral public search boundary shared by discovery capabilities."""

from __future__ import annotations

from typing import Protocol

from mia_dpp.domain.base import WireModel


class SearchHit(WireModel):
    title: str
    url: str
    snippet: str = ""


class SearchProvider(Protocol):
    async def search(self, query: str, *, limit: int = 8) -> tuple[SearchHit, ...]: ...


class SearchUnavailableError(RuntimeError):
    """A public search provider was unavailable or returned malformed data."""
