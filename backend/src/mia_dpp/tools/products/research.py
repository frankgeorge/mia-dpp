"""Find additional public sources for an already identified product."""

from __future__ import annotations

import hashlib
from urllib.parse import urlsplit

from mia_dpp.domain.discovery import ProductSourceCandidate
from mia_dpp.tools.search import SearchProvider


class ProductResearchTool:
    """Find additional source pages for one identified product.

    MIA agent uses this after coverage reveals gaps. Results record whether each
    page belongs to the known manufacturer domain before later extraction.
    """

    def __init__(self, search: SearchProvider) -> None:
        self._search = search

    async def search(
        self,
        *,
        product_id: str,
        product_name: str,
        query: str,
        manufacturer_domain: str | None,
    ) -> tuple[ProductSourceCandidate, ...]:
        """Return new source candidates with explicit manufacturer-domain authority."""

        scope = " ".join(part for part in (product_name, query.strip()) if part)
        if manufacturer_domain:
            scope = f"site:{manufacturer_domain} {scope}"
        hits = await self._search.search(scope, limit=12)
        results: list[ProductSourceCandidate] = []
        seen: set[str] = set()
        for hit in hits:
            url = hit.url.split("#", maxsplit=1)[0]
            if url in seen:
                continue
            seen.add(url)
            host = (urlsplit(url).hostname or "").removeprefix("www.").casefold()
            authoritative = bool(
                manufacturer_domain
                and (host == manufacturer_domain or host.endswith("." + manufacturer_domain))
            )
            seed = f"{product_id}\0{url}"
            results.append(
                ProductSourceCandidate(
                    id="source-" + hashlib.sha256(seed.encode()).hexdigest()[:20],
                    product_id=product_id,
                    title=hit.title[:240],
                    url=url,
                    description=hit.snippet[:600],
                    authoritative_domain=authoritative,
                    source_uri=hit.url,
                )
            )
        return tuple(results)
