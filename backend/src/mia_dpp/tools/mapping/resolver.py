"""Deterministically resolve collected evidence against official targets."""

from __future__ import annotations

from datetime import UTC, datetime

from mia_dpp.aas.requirements import build_template_index
from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.domain.evidence import ProductKnowledgePackage
from mia_dpp.domain.mappings import GraphEntry
from mia_dpp.domain.workflow import WorkflowEvent, completed_event
from mia_dpp.tools.mapping.catalog import nameplate_catalog
from mia_dpp.tools.mapping.coverage import CoverageAnalyzer
from mia_dpp.tools.mapping.mapper import DeterministicWebsiteMapper
from mia_dpp.tools.mapping.models import WebsiteIngestRequest, WebsiteIngestResponse
from mia_dpp.tools.web.models import WebExtractionResult
from mia_dpp.tools.web.tool import WebExtractionTool


async def resolve_product(
    package: ProductKnowledgePackage,
    repository: OfficialTemplateRepository,
    *,
    template_keys: tuple[str, ...],
    graph: tuple[GraphEntry, ...] = (),
    source_url: str = "",
    workflow_events: tuple[WorkflowEvent, ...] = (),
) -> WebsiteIngestResponse:
    """Map one source-neutral knowledge package and derive its coverage."""

    evidence = package.evidence
    events = list(workflow_events)

    started = datetime.now(UTC)
    templates = tuple(repository.load(key) for key in template_keys)
    events.append(
        completed_event(
            stage="templates.load",
            started_at=started,
            input_count=len(template_keys),
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

    started = datetime.now(UTC)
    index = build_template_index(templates)
    events.append(
        completed_event(
            stage="requirements.build",
            started_at=started,
            input_count=len(templates),
            output_count=len(index.requirements),
            summary=(
                f"Indexed {len(index.requirements)} targets from official template metadata."
            ),
        )
    )

    history = {
        (entry.source_field.casefold(), entry.target_element): max(entry.corrections, 1)
        for entry in graph
    }
    started = datetime.now(UTC)
    mapping = await DeterministicWebsiteMapper(repository).propose(evidence, history=history)
    proposals = (*mapping.mapped, *mapping.ambiguous)
    events.append(
        completed_event(
            stage="mapping.deterministic",
            started_at=started,
            input_count=len(evidence),
            output_count=len(proposals),
            summary=(
                f"Mapped {len(mapping.mapped)}, marked {len(mapping.ambiguous)} ambiguous, "
                f"and retained {len(mapping.unmatched_evidence_ids)} unmatched."
            ),
            metadata={
                "mapped": len(mapping.mapped),
                "ambiguous": len(mapping.ambiguous),
                "unmatched": len(mapping.unmatched_evidence_ids),
            },
        )
    )

    started = datetime.now(UTC)
    coverage = CoverageAnalyzer().analyze(package, index, mapping_result=mapping)
    statistics = coverage.statistics
    events.append(
        completed_event(
            stage="coverage.analyze",
            started_at=started,
            input_count=len(evidence) + len(index.requirements),
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
            f"MIA retained {len(evidence)} facts from {source_url or 'the product sources'}: "
            f"{len(mapping.mapped)} deterministically mapped, "
            f"{len(mapping.ambiguous)} ambiguous, and "
            f"{len(mapping.unmatched_evidence_ids)} currently unmatched."
        ),
        source_url=source_url,
        knowledge_package=package,
        mapping_result=mapping,
        template_index=index,
        workflow_events=tuple(events),
        nameplate_elements=nameplate_catalog(repository),
    )


async def resolve_extraction(
    extraction: WebExtractionResult,
    repository: OfficialTemplateRepository,
    request: WebsiteIngestRequest,
) -> WebsiteIngestResponse:
    """Resolve an existing web extraction without coupling mapping to crawling."""

    return await resolve_product(
        extraction.knowledge_package,
        repository,
        template_keys=request.template_keys,
        graph=request.graph,
        source_url=extraction.source_url,
        workflow_events=extraction.workflow_events,
    )


async def ingest_website(
    request: WebsiteIngestRequest,
    web: WebExtractionTool,
    repository: OfficialTemplateRepository,
) -> WebsiteIngestResponse:
    """Compose extraction and resolution for the direct website API."""

    return await resolve_extraction(await web.extract(request.url), repository, request)
