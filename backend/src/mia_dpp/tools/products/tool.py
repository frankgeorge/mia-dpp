"""Discover manufacturer-owned product pages as structured candidates."""

from __future__ import annotations

import hashlib
from urllib.parse import urlsplit

from mia_dpp.domain.discovery import CompanyCandidate, ProductCandidate
from mia_dpp.tools.search import SearchProvider


class ProductDiscoveryTool:
    def __init__(self, search: SearchProvider) -> None:
        self._search = search

    async def discover(
        self,
        company: CompanyCandidate,
        *,
        query: str = "",
    ) -> tuple[ProductCandidate, ...]:
        scope = query.strip() or "industrial products catalogue"
        hits = await self._search.search(f"site:{company.domain} {scope}", limit=16)
        candidates: list[ProductCandidate] = []
        seen: set[str] = set()
        for hit in hits:
            parsed = urlsplit(hit.url)
            host = (parsed.hostname or "").removeprefix("www.").casefold()
            if not (host == company.domain or host.endswith("." + company.domain)):
                continue
            normalized_url = hit.url.split("#", maxsplit=1)[0]
            if normalized_url in seen:
                continue
            seen.add(normalized_url)
            seed = f"{company.id}\0{normalized_url}"
            candidates.append(
                ProductCandidate(
                    id="product-" + hashlib.sha256(seed.encode()).hexdigest()[:20],
                    name=hit.title[:200],
                    official_url=normalized_url,
                    description=hit.snippet[:500],
                    source_uri=hit.url,
                )
            )
        return tuple(candidates[:12])
