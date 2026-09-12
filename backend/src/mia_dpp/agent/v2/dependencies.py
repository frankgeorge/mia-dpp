"""Runtime dependencies injected into every PydanticAI tool call."""

from dataclasses import dataclass

from mia_dpp.aas.build import DeterministicDppPipeline
from mia_dpp.agent.v2.models import MiaState
from mia_dpp.tools.company.tool import CompanyDiscoveryTool
from mia_dpp.tools.mapping.resolver import ProductResolver
from mia_dpp.tools.products.tool import ProductDiscoveryTool
from mia_dpp.tools.web.tool import WebExtractionTool


@dataclass
class MiaDependencies:
    state: MiaState
    company_tool: CompanyDiscoveryTool
    product_tool: ProductDiscoveryTool
    web_tool: WebExtractionTool
    mapping_tool: ProductResolver
    dpp_pipeline: DeterministicDppPipeline
