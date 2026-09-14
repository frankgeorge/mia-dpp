"""Deterministically resolve collected evidence against official targets."""

from __future__ import annotations

from mia_dpp.aas.requirements import build_template_index
from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.domain.evidence import ProductKnowledgePackage
from mia_dpp.tools.mapping.catalog import nameplate_catalog
from mia_dpp.tools.mapping.coverage import coverage
from mia_dpp.tools.mapping.mapper import DeterministicWebsiteMapper
from mia_dpp.tools.mapping.models import ProductResolution


async def resolve_product(
    package: ProductKnowledgePackage,
    repository: OfficialTemplateRepository,
    *,
    template_keys: tuple[str, ...],
) -> ProductResolution:
    """Map one source-neutral knowledge package and expose derived coverage."""

    templates = tuple(repository.load(key) for key in template_keys)
    index = build_template_index(templates)
    mapping = await DeterministicWebsiteMapper(repository).propose(package.evidence)
    # Evaluate once here so invalid accounting fails before the result is returned.
    coverage(package, index, mapping_result=mapping)
    return ProductResolution(
        knowledge_package=package,
        mapping_result=mapping,
        template_index=index,
        nameplate_elements=nameplate_catalog(repository),
    )
