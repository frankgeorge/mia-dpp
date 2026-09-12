"""Deterministic resolution of collected evidence against official targets."""

from __future__ import annotations

from datetime import UTC, datetime

from mia_dpp.aas.requirements import build_requirement_inventory
from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.domain.completion import build_completion_summary
from mia_dpp.domain.mappings import MappingProposal
from mia_dpp.domain.workflow import completed_event
from mia_dpp.tools.mapping.catalog import nameplate_catalog
from mia_dpp.tools.mapping.coverage import CoverageAnalyzer
from mia_dpp.tools.mapping.mapper import DeterministicWebsiteMapper, MappingStrategy
from mia_dpp.tools.mapping.models import WebsiteIngestRequest, WebsiteIngestResponse
from mia_dpp.tools.web.models import WebExtractionResult
from mia_dpp.tools.web.tool import WebExtractionTool


class ProductResolver:
    """Compare an existing evidence package with explicitly selected templates."""

    def __init__(
        self,
        repository: OfficialTemplateRepository,
        *,
        mapping_strategy: MappingStrategy | None = None,
        coverage_analyzer: CoverageAnalyzer | None = None,
    ) -> None:
        self._repository = repository
        self._mapping_strategy = mapping_strategy or DeterministicWebsiteMapper(repository)
        self._coverage_analyzer = coverage_analyzer or CoverageAnalyzer()

    async def resolve(
        self,
        extraction: WebExtractionResult,
        request: WebsiteIngestRequest,
    ) -> WebsiteIngestResponse:
        package = extraction.knowledge_package
        evidence = package.evidence
        events = list(extraction.workflow_events)

        templates_started = datetime.now(UTC)
        templates = tuple(self._repository.load(key) for key in request.template_keys)
        events.append(
            completed_event(
                stage="templates.load",
                started_at=templates_started,
                input_count=len(request.template_keys),
                output_count=len(templates),
                summary=f"Loaded {len(templates)} pinned official IDTA templates.",
                metadata={
                    "templates": [
                        {"key": item.release.key, "release": item.release.release}
                        for item in templates
                    ]
                },
            )
        )

        requirements_started = datetime.now(UTC)
        inventory = build_requirement_inventory(templates)
        events.append(
            completed_event(
                stage="requirements.build",
                started_at=requirements_started,
                input_count=len(templates),
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
        coverage = self._coverage_analyzer.analyze(
            package,
            inventory,
            mapping_result=mapping_result,
        )
        completion = build_completion_summary(coverage, mapping_result, evidence)
        statistics = coverage.statistics
        events.append(
            completed_event(
                stage="coverage.analyze",
                started_at=coverage_started,
                input_count=len(evidence) + len(inventory.requirements),
                output_count=len(coverage.coverage),
                summary=(
                    f"Coverage has {statistics.required_satisfied} required satisfied, "
                    f"{statistics.required_candidate} candidate, "
                    f"{statistics.required_ambiguous} ambiguous, and "
                    f"{statistics.required_missing} missing."
                ),
                metadata={
                    "satisfied": statistics.required_satisfied + statistics.optional_satisfied,
                    "candidate": statistics.required_candidate + statistics.optional_candidate,
                    "ambiguous": statistics.required_ambiguous + statistics.optional_ambiguous,
                    "missing": statistics.required_missing + statistics.optional_missing,
                    "unmatchedEvidence": statistics.unmatched_evidence,
                },
            )
        )
        return WebsiteIngestResponse(
            reply=(
                f"Crawl4AI fetched {extraction.source_url}. MIA retained {len(evidence)} facts: "
                f"{len(mapping_result.mapped)} deterministically mapped, "
                f"{len(mapping_result.ambiguous)} ambiguous, and "
                f"{len(mapping_result.unmatched_evidence_ids)} currently unmatched."
            ),
            source_url=extraction.source_url,
            proposal=MappingProposal(product_name=extraction.product_name, mappings=proposals),
            evidence=evidence,
            knowledge_package=package,
            mapping_result=mapping_result,
            coverage_report=coverage,
            completion_summary=completion,
            workflow_events=tuple(events),
            nameplate_elements=nameplate_catalog(self._repository),
        )


class WebsiteWorkflow:
    """Small coordinator retained for the direct website API use case."""

    def __init__(self, web_tool: WebExtractionTool, resolver: ProductResolver) -> None:
        self._web_tool = web_tool
        self._resolver = resolver

    async def ingest(self, request: WebsiteIngestRequest) -> WebsiteIngestResponse:
        extraction = await self._web_tool.extract(request.url)
        return await self._resolver.resolve(extraction, request)
