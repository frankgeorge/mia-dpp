"""Runtime dependencies injected into every PydanticAI tool call."""

from dataclasses import dataclass

from mia_dpp.aas.build import DeterministicDppPipeline
from mia_dpp.agent.v2.models import MiaState
from mia_dpp.tools.company.tool import CompanyDiscoveryTool
from mia_dpp.tools.mapping.resolver import ProductResolver
from mia_dpp.tools.mapping.review import MappingReviewService
from mia_dpp.tools.products.research import ProductResearchTool
from mia_dpp.tools.products.tool import ProductDiscoveryTool
from mia_dpp.tools.web.tool import WebExtractionTool


@dataclass
class MiaDependencies:
    """Capabilities injected into every PydanticAI tool call.

    Tools use this object to read or update the current ``MiaState`` and to
    invoke MIA services assembled by ``bootstrap``. The model never constructs
    these trusted dependencies itself.
    """

    state: MiaState
    company_tool: CompanyDiscoveryTool
    product_tool: ProductDiscoveryTool
    product_research_tool: ProductResearchTool
    web_tool: WebExtractionTool
    mapping_tool: ProductResolver
    mapping_review: MappingReviewService
    dpp_pipeline: DeterministicDppPipeline
