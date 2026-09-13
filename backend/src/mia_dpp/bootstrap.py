"""Composition root: connect MIA roles, tools, core logic, and integrations."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from mia_dpp.aas.build import DeterministicDppPipeline
from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.agent.brain import AutonomousAgent
from mia_dpp.agent.graph import MiaAgent
from mia_dpp.config import Settings
from mia_dpp.integrations.crawl4ai import Crawl4AIPageLoader
from mia_dpp.integrations.ddgs import DdgsSearchProvider
from mia_dpp.tools.company.tool import CompanyDiscoveryTool
from mia_dpp.tools.mapping.knowledge import MappingKnowledgeStore
from mia_dpp.tools.mapping.resolver import ProductResolver, WebsiteWorkflow
from mia_dpp.tools.mapping.review import MappingReviewService
from mia_dpp.tools.products.research import ProductResearchTool
from mia_dpp.tools.products.tool import ProductDiscoveryTool
from mia_dpp.tools.web.tool import WebExtractionTool
from mia_dpp.workspace.store import FileWorkspaceStore


@dataclass(frozen=True)
class Application:
    """Concrete capabilities shared by the HTTP routes.

    ``build_application`` creates this object once at startup. Routes retrieve
    it from FastAPI state instead of constructing tools or integrations.
    """

    settings: Settings
    templates: OfficialTemplateRepository
    web_tool: WebExtractionTool
    resolver: ProductResolver
    website_workflow: WebsiteWorkflow
    agent: MiaAgent
    workspace: FileWorkspaceStore
    mapping_knowledge: MappingKnowledgeStore


def build_application(settings: Settings | None = None) -> Application:
    """Connect MIA's concrete implementations at application startup.

    This composition root wires OpenRouter/PydanticAI, Crawl4AI, DDGS, the
    thread store, mapping services, and deterministic AAS pipeline. It returns
    the ``Application`` used by ``create_app`` and contains no workflow policy.
    """

    configured = settings or Settings()
    templates = OfficialTemplateRepository(configured.standards_root)
    web_tool = WebExtractionTool(loader=Crawl4AIPageLoader())
    resolver = ProductResolver(templates)
    website_workflow = WebsiteWorkflow(web_tool, resolver)
    search = DdgsSearchProvider()
    company_tool = CompanyDiscoveryTool(search)
    product_tool = ProductDiscoveryTool(search)
    product_research_tool = ProductResearchTool(search)

    agent_model = None
    if configured.openrouter_api_key is not None:
        api_key = configured.openrouter_api_key.get_secret_value()
        agent_model = OpenRouterModel(
            configured.agent_model,
            provider=OpenRouterProvider(
                api_key=api_key,
                app_url="https://mia-dpp.vercel.app",
                app_title="MIA Digital Product Passport",
            ),
        )
    workspace = FileWorkspaceStore(configured.workspace_root)
    mapping_review = MappingReviewService(templates)
    mapping_knowledge = MappingKnowledgeStore(
        configured.thread_store_path.with_name(
            configured.thread_store_path.stem + "-mapping-knowledge.sqlite3"
        )
    )
    brain = AutonomousAgent(
        model=agent_model,
        company_tool=company_tool,
        product_tool=product_tool,
        product_research_tool=product_research_tool,
        web_tool=web_tool,
        mapping_tool=resolver,
        mapping_review=mapping_review,
        mapping_knowledge=mapping_knowledge,
        dpp_pipeline=DeterministicDppPipeline(templates),
        workspace=workspace,
    )
    agent = MiaAgent(
        brain=brain,
        mapping_review=mapping_review,
        mapping_knowledge=mapping_knowledge,
        workspace=workspace,
        database_path=configured.thread_store_path,
    )
    return Application(
        settings=configured,
        templates=templates,
        web_tool=web_tool,
        resolver=resolver,
        website_workflow=website_workflow,
        agent=agent,
        workspace=workspace,
        mapping_knowledge=mapping_knowledge,
    )
