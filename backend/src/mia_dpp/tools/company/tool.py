"""Turn public search results into structured candidate manufacturers."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit

from mia_dpp.domain.discovery import CompanyCandidate
from mia_dpp.tools.search import SearchProvider

_TITLE_SUFFIX = re.compile(
    r"\s*(?:[-|:]\s*)?(?:official(?:\s+website)?|homepage|global|products?).*$",
    re.IGNORECASE,
)


class CompanyDiscoveryTool:
    def __init__(self, search: SearchProvider) -> None:
        self._search = search

    async def search(self, company_name: str) -> tuple[CompanyCandidate, ...]:
        hits = await self._search.search(
            f"{company_name} manufacturer official website company",
            limit=10,
        )
        candidates: list[CompanyCandidate] = []
        seen_domains: set[str] = set()
        for hit in hits:
            parsed = urlsplit(hit.url)
            domain = (parsed.hostname or "").removeprefix("www.").casefold()
            if not domain or domain in seen_domains:
                continue
            seen_domains.add(domain)
            name = _TITLE_SUFFIX.sub("", hit.title).strip(" -|:") or hit.title
            seed = f"{name.casefold()}\0{domain}"
            candidates.append(
                CompanyCandidate(
                    id="company-" + hashlib.sha256(seed.encode()).hexdigest()[:20],
                    name=name[:160],
                    official_url=f"{parsed.scheme or 'https'}://{parsed.netloc}/",
                    domain=domain,
                    description=hit.snippet[:400],
                    source_uri=hit.url,
                )
            )
        return tuple(candidates[:6])
