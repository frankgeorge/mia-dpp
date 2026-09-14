"""Deterministically resolve collected evidence against official targets."""

from __future__ import annotations

from mia_dpp.aas.requirements import build_template_index
from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.domain.evidence import ProductKnowledgePackage
from mia_dpp.tools.mapping.catalog import nameplate_catalog
from mia_dpp.tools.mapping.coverage import coverage
from mia_dpp.tools.mapping.mapper import DeterministicWebsiteMapper
from mia_dpp.tools.mapping.models import WebsiteIngestResponse


async def resolve_product(
    package: ProductKnowledgePackage,
    repository: OfficialTemplateRepository,
    *,
    template_keys: tuple[str, ...],
    source_url: str = "",
) -> WebsiteIngestResponse:
    """Map one source-neutral knowledge package and expose derived coverage."""

    templates = tuple(repository.load(key) for key in template_keys)
    index = build_template_index(templates)
    mapping = await DeterministicWebsiteMapper(repository).propose(package.evidence)
    # Evaluate once here so invalid accounting fails before the result is returned.
    coverage(package, index, mapping_result=mapping)
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
