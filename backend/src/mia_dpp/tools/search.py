"""Shared public search boundary and MIA-specific result projections."""

from __future__ import annotations

import hashlib
import re
from typing import Protocol
from urllib.parse import urlsplit

from mia_dpp.domain.base import WireModel
from mia_dpp.domain.discovery import CompanyCandidate, ProductCandidate, ProductSourceCandidate

_TITLE_SUFFIX = re.compile(
    r"\s*(?:[-|:]\s*)?(?:official(?:\s+website)?|homepage|global|products?).*$",
    re.IGNORECASE,
)


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


async def find_companies(search: SearchProvider, company_name: str) -> tuple[CompanyCandidate, ...]:
    """Project public results into deduplicated company candidates."""

    hits = await search.search(f"{company_name} manufacturer official website company", limit=10)
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


async def find_products(
    search: SearchProvider,
    company: CompanyCandidate,
    *,
    query: str = "",
) -> tuple[ProductCandidate, ...]:
    """Project search results into product candidates on a verified domain."""

    scope = query.strip() or "industrial products catalogue"
    hits = await search.search(f"site:{company.domain} {scope}", limit=16)
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


async def find_product_sources(
    search: SearchProvider,
    *,
    product_id: str,
    product_name: str,
    query: str,
    manufacturer_domain: str | None,
) -> tuple[ProductSourceCandidate, ...]:
    """Find more sources and mark verified manufacturer-owned results."""

    scope = " ".join(part for part in (product_name, query.strip()) if part)
    if manufacturer_domain:
        scope = f"site:{manufacturer_domain} {scope}"
    hits = await search.search(scope, limit=12)
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
