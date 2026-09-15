"""The agent-facing capability that turns one URL into source evidence."""

from __future__ import annotations

import hashlib

from mia_dpp.domain.evidence import ProductKnowledgePackage
from mia_dpp.errors import ExtractionError
from mia_dpp.tools.web.generic import WebsiteFactExtractor
from mia_dpp.tools.web.models import PageLoader, RenderedPage
from mia_dpp.tools.web.url_policy import ProductUrlPolicy


class WebExtractionTool:
    """Turn one public URL into provenance-rich product evidence.

    MIA agent or the direct website workflow calls this capability. It validates
    and loads the page, extracts facts, and normalizes evidence, but never maps
    facts to AAS targets.
    """

    def __init__(
        self,
        *,
        loader: PageLoader,
        url_policy: ProductUrlPolicy | None = None,
        fact_extractor: WebsiteFactExtractor | None = None,
    ) -> None:
        self._loader = loader
        self._url_policy = url_policy or ProductUrlPolicy()
        self._fact_extractor = fact_extractor or WebsiteFactExtractor()

    async def extract(self, url: str) -> ProductKnowledgePackage:
        """Acquire, extract, and normalize one page into a product knowledge package."""

        requested_url = await self._url_policy.validate(url)
        page = await self._loader.load(requested_url)
        final_url = await self._url_policy.validate(page.url)
        if final_url != page.url:
            page = RenderedPage(url=final_url, html=page.html, acquired_at=page.acquired_at)
        evidence, product_name = self._fact_extractor.extract(page)
        if not evidence:
            raise ExtractionError("the product page contained no useful structured facts")
        source_id = f"source-web-{page.content_sha256[:24]}"
        return ProductKnowledgePackage(
            product_id="product-"
            + hashlib.sha256(f"{page.url}\0{product_name}".encode()).hexdigest()[:24],
            product_name=product_name,
            source_artifact_ids=(source_id,),
            evidence=evidence,
        )
