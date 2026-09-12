"""DDGS metasearch implementation used for key-free public discovery."""

from __future__ import annotations

import asyncio
from typing import Any

from ddgs import DDGS

from mia_dpp.tools.search import SearchHit, SearchUnavailableError


class DdgsSearchProvider:
    def __init__(self, *, timeout: int = 10) -> None:
        self._timeout = timeout

    async def search(self, query: str, *, limit: int = 8) -> tuple[SearchHit, ...]:
        try:
            rows = await asyncio.to_thread(self._search, query, limit)
        except Exception as error:
            raise SearchUnavailableError(f"public search failed: {error}") from error
        hits: list[SearchHit] = []
        for row in rows:
            url = row.get("href") or row.get("url")
            title = row.get("title")
            if not isinstance(url, str) or not isinstance(title, str):
                continue
            hits.append(
                SearchHit(
                    title=title.strip(),
                    url=url.strip(),
                    snippet=str(row.get("body") or row.get("description") or "").strip(),
                )
            )
        return tuple(hits)

    def _search(self, query: str, limit: int) -> list[dict[str, Any]]:
        return DDGS(timeout=self._timeout).text(
            query,
            max_results=limit,
            safesearch="moderate",
        )
