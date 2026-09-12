"""The agent-facing capability that turns one URL into source evidence."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from mia_dpp.domain.evidence import ProductKnowledgePackage
from mia_dpp.domain.workflow import completed_event
from mia_dpp.errors import ExtractionError
from mia_dpp.tools.web.artifacts import raw_website_artifact
from mia_dpp.tools.web.generic import WebsiteFactExtractor
from mia_dpp.tools.web.models import PageLoader, RenderedPage, WebExtractionResult
from mia_dpp.tools.web.normalizer import EvidenceNormalizer
from mia_dpp.tools.web.url_policy import ProductUrlPolicy


class WebExtractionTool:
    """Acquire and normalize web evidence without interpreting AAS targets."""

    def __init__(
        self,
        *,
        loader: PageLoader | None = None,
        url_policy: ProductUrlPolicy | None = None,
        fact_extractor: WebsiteFactExtractor | None = None,
        evidence_normalizer: EvidenceNormalizer | None = None,
    ) -> None:
        if loader is None:
            from mia_dpp.integrations.crawl4ai import Crawl4AIPageLoader

            loader = Crawl4AIPageLoader()
        self._loader = loader
        self._url_policy = url_policy or ProductUrlPolicy()
        self._fact_extractor = fact_extractor or WebsiteFactExtractor()
        self._evidence_normalizer = evidence_normalizer or EvidenceNormalizer()

    async def extract(self, url: str) -> WebExtractionResult:
        events = []
        fetch_started = datetime.now(UTC)
        requested_url = await self._url_policy.validate(url)
        page = await self._loader.load(requested_url)
        final_url = await self._url_policy.validate(page.url)
        if final_url != page.url:
            page = RenderedPage(url=final_url, html=page.html, acquired_at=page.acquired_at)
        source = raw_website_artifact(page)
        events.append(
            completed_event(
                stage="source.fetch",
                started_at=fetch_started,
                input_count=1,
                output_count=1,
                summary=f"Fetched one HTML source from {page.url}.",
                metadata={"contentSha256": source.content_sha256},
            )
        )

        extraction_started = datetime.now(UTC)
        facts, product_name = self._fact_extractor.extract(source)
        if not facts:
            raise ExtractionError("the product page contained no useful structured facts")
        events.append(
            completed_event(
                stage="facts.extract",
                started_at=extraction_started,
                input_count=1,
                output_count=len(facts),
                summary=f"Extracted {len(facts)} source-labelled candidate facts.",
            )
        )

        normalization_started = datetime.now(UTC)
        evidence = self._evidence_normalizer.normalize(source, facts)
        package = ProductKnowledgePackage(
            product_id="product-"
            + hashlib.sha256(f"{page.url}\0{product_name}".encode()).hexdigest()[:24],
            product_name=product_name,
            source_artifact_ids=(source.id,),
            evidence=evidence,
        )
        events.append(
            completed_event(
                stage="evidence.normalize",
                started_at=normalization_started,
                input_count=len(facts),
                output_count=len(evidence),
                summary=f"Retained all {len(evidence)} facts as provenance-rich evidence.",
            )
        )
        return WebExtractionResult(
            source_url=page.url,
            product_name=product_name,
            knowledge_package=package,
            workflow_events=tuple(events),
        )
