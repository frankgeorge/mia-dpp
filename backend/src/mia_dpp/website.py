"""Orchestrate product-page acquisition, fact retention, and downstream mapping."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from mia_dpp.chat import nameplate_catalog
from mia_dpp.completion import build_completion_summary
from mia_dpp.coverage import CoverageAnalyzer
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
from mia_dpp.requirements import build_requirement_inventory
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
        coverage_analyzer: CoverageAnalyzer | None = None,
    ) -> None:
        self._repository = repository
        self._loader = loader or Crawl4AIPageLoader()
        self._url_policy = url_policy or ProductUrlPolicy()
        self._fact_extractor = fact_extractor or WebsiteFactExtractor()
        self._evidence_normalizer = evidence_normalizer or EvidenceNormalizer()
        self._mapping_strategy = mapping_strategy or DeterministicWebsiteMapper(repository)
        self._coverage_analyzer = coverage_analyzer or CoverageAnalyzer()

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

        templates_started = datetime.now(UTC)
        selected_templates = tuple(self._repository.load(key) for key in request.template_keys)
        events.append(
            completed_event(
                stage="templates.load",
                started_at=templates_started,
                input_count=len(request.template_keys),
                output_count=len(selected_templates),
                summary=f"Loaded {len(selected_templates)} pinned official IDTA templates.",
                metadata={
                    "templates": [
                        {
                            "key": template.release.key,
                            "release": template.release.release,
                        }
                        for template in selected_templates
                    ]
                },
            )
        )

        requirements_started = datetime.now(UTC)
        inventory = build_requirement_inventory(selected_templates)
        events.append(
            completed_event(
                stage="requirements.build",
                started_at=requirements_started,
                input_count=len(selected_templates),
                output_count=len(inventory.requirements),
                summary=(
                    f"Built {len(inventory.requirements)} stable requirements from official "
                    "template metadata."
                ),
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

        coverage_started = datetime.now(UTC)
        coverage_report = self._coverage_analyzer.analyze(
            package,
            inventory,
            mapping_result=mapping_result,
        )
        completion_summary = build_completion_summary(coverage_report, mapping_result)
        statistics = coverage_report.statistics
        events.append(
            completed_event(
                stage="coverage.analyze",
                started_at=coverage_started,
                input_count=len(evidence) + len(inventory.requirements),
                output_count=len(coverage_report.coverage),
                summary=(
                    f"Coverage has {statistics.required_satisfied} required satisfied, "
                    f"{statistics.required_candidate} candidate, "
                    f"{statistics.required_ambiguous} ambiguous, and "
                    f"{statistics.required_missing} missing."
                ),
                metadata={
                    "satisfied": (statistics.required_satisfied + statistics.optional_satisfied),
                    "candidate": (statistics.required_candidate + statistics.optional_candidate),
                    "ambiguous": (statistics.required_ambiguous + statistics.optional_ambiguous),
                    "missing": statistics.required_missing + statistics.optional_missing,
                    "unmatchedEvidence": statistics.unmatched_evidence,
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
            coverage_report=coverage_report,
            completion_summary=completion_summary,
            workflow_events=tuple(events),
            nameplate_elements=nameplate_catalog(self._repository),
        )
