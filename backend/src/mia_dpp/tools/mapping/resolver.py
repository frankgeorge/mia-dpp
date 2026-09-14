"""Deterministically resolve collected evidence against official targets."""

from __future__ import annotations

from mia_dpp.aas.requirements import build_template_index
from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.domain.evidence import ProductKnowledgePackage
from mia_dpp.domain.mappings import GraphEntry
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
) -> WebsiteIngestResponse:
    """Map one source-neutral knowledge package and expose derived coverage."""

    templates = tuple(repository.load(key) for key in template_keys)
    index = build_template_index(templates)
    history = {
        (entry.source_field.casefold(), entry.target_element): max(entry.corrections, 1)
        for entry in graph
    }
    mapping = await DeterministicWebsiteMapper(repository).propose(
        package.evidence, history=history
    )
    # Evaluate once here so invalid accounting fails before the result is returned.
    CoverageAnalyzer().analyze(package, index, mapping_result=mapping)
    return WebsiteIngestResponse(
        reply=(
            f"MIA retained {len(package.evidence)} facts from "
            f"{source_url or 'the product sources'}: "
            f"{len(mapping.mapped)} deterministically mapped, "
            f"{len(mapping.ambiguous)} ambiguous, and "
            f"{len(mapping.unmatched_evidence_ids)} currently unmatched."
        ),
        source_url=source_url,
        knowledge_package=package,
        mapping_result=mapping,
        template_index=index,
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
    )


async def ingest_website(
    request: WebsiteIngestRequest,
    web: WebExtractionTool,
    repository: OfficialTemplateRepository,
) -> WebsiteIngestResponse:
    """Compose extraction and resolution for the direct website API."""

    return await resolve_extraction(await web.extract(request.url), repository, request)
