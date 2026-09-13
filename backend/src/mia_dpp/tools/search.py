"""Provider-neutral public search boundary shared by discovery capabilities."""

from __future__ import annotations

from typing import Protocol

from mia_dpp.domain.base import WireModel


class SearchHit(WireModel):
    """Provider-neutral public search result used by discovery tools."""

    title: str
    url: str
    snippet: str = ""


class SearchProvider(Protocol):
    """Boundary separating MIA discovery tools from a search vendor."""

    async def search(self, query: str, *, limit: int = 8) -> tuple[SearchHit, ...]:
        """Return normalized public results for a company or product query."""

        ...


class SearchUnavailableError(RuntimeError):
    """A public search provider was unavailable or returned malformed data."""
