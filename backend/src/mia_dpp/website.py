"""Orchestrate product-page acquisition, fact retention, and downstream mapping."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from mia_dpp.chat import nameplate_catalog
from mia_dpp.errors import ExtractionError
from mia_dpp.evidence import EvidenceNormalizer
from mia_dpp.extraction import Crawl4AIPageLoader, PageLoader, RenderedPage
from mia_dpp.models import (
    MappingProposal,
    ProductKnowledgePackage,
    WebsiteIngestRequest,
    WebsiteIngestResponse,
    WorkflowEvent,
)
from mia_dpp.source_artifacts import raw_website_artifact
from mia_dpp.templates import OfficialTemplateRepository
from mia_dpp.url_policy import ProductUrlPolicy
from mia_dpp.website_facts import WebsiteFactExtractor
from mia_dpp.website_mapping import DeterministicWebsiteMapper, MappingStrategy
from mia_dpp.workflow import completed_event


class WebsiteIngestionService:
    """Compose independent acquisition, extraction, normalization, and mapping stages."""

    def __init__(
        self,
        repository: OfficialTemplateRepository,
        *,
        loader: PageLoader | None = None,
        url_policy: ProductUrlPolicy | None = None,
        fact_extractor: WebsiteFactExtractor | None = None,
        evidence_normalizer: EvidenceNormalizer | None = None,
        mapping_strategy: MappingStrategy | None = None,
    ) -> None:
        self._repository = repository
        self._loader = loader or Crawl4AIPageLoader()
        self._url_policy = url_policy or ProductUrlPolicy()
        self._fact_extractor = fact_extractor or WebsiteFactExtractor()
        self._evidence_normalizer = evidence_normalizer or EvidenceNormalizer()
        self._mapping_strategy = mapping_strategy or DeterministicWebsiteMapper(repository)

    async def ingest(self, request: WebsiteIngestRequest) -> WebsiteIngestResponse:
        events: list[WorkflowEvent] = []

        fetch_started = datetime.now(UTC)
        requested_url = await self._url_policy.validate(request.url)
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

        mapping_started = datetime.now(UTC)
        history = {
            (entry.source_field.casefold(), entry.target_element): max(entry.corrections, 1)
            for entry in request.graph
        }
        mapping_result = await self._mapping_strategy.propose(evidence, history=history)
        proposals = (*mapping_result.mapped, *mapping_result.ambiguous)
        events.append(
            completed_event(
                stage="mapping.deterministic",
                started_at=mapping_started,
                input_count=len(evidence),
                output_count=len(proposals),
                summary=(
                    f"Mapped {len(mapping_result.mapped)}, marked "
                    f"{len(mapping_result.ambiguous)} ambiguous, and retained "
                    f"{len(mapping_result.unmatched_evidence_ids)} unmatched."
                ),
                metadata={
                    "mapped": len(mapping_result.mapped),
                    "ambiguous": len(mapping_result.ambiguous),
                    "unmatched": len(mapping_result.unmatched_evidence_ids),
                },
            )
        )

        return WebsiteIngestResponse(
            reply=(
                f"Crawl4AI fetched {page.url}. MIA retained {len(evidence)} facts: "
                f"{len(mapping_result.mapped)} deterministically mapped, "
                f"{len(mapping_result.ambiguous)} ambiguous, and "
                f"{len(mapping_result.unmatched_evidence_ids)} currently unmatched."
            ),
            source_url=page.url,
            proposal=MappingProposal(product_name=product_name, mappings=proposals),
            evidence=evidence,
            knowledge_package=package,
            mapping_result=mapping_result,
            workflow_events=tuple(events),
            nameplate_elements=nameplate_catalog(self._repository),
        )
