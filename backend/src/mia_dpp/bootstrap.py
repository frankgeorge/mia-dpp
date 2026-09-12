"""Composition root: connect MIA roles, tools, core logic, and integrations."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from mia_dpp.aas.build import DeterministicDppPipeline
from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.agent.graph import MiaAgentWorkflow
from mia_dpp.agent.v2.runtime import MiaAgentV2
from mia_dpp.agent.v2.store import SQLiteThreadStore
from mia_dpp.config import Settings
from mia_dpp.integrations.crawl4ai import Crawl4AIPageLoader
from mia_dpp.integrations.ddgs import DdgsSearchProvider
from mia_dpp.integrations.openrouter import OpenRouterClient
from mia_dpp.llm.chat import ChatLLM, ChatModel, UnconfiguredChatLLM
from mia_dpp.llm.semantic import SemanticLLM, SemanticModel, UnconfiguredSemanticLLM
from mia_dpp.tools.company.tool import CompanyDiscoveryTool
from mia_dpp.tools.mapping.resolver import ProductResolver, WebsiteWorkflow
from mia_dpp.tools.products.tool import ProductDiscoveryTool
from mia_dpp.tools.web.tool import WebExtractionTool


@dataclass(frozen=True)
class Application:
    settings: Settings
    templates: OfficialTemplateRepository
    web_tool: WebExtractionTool
    resolver: ProductResolver
    website_workflow: WebsiteWorkflow
    chat_llm: ChatModel
    semantic_llm: SemanticModel
    agent_workflow: MiaAgentWorkflow
    agent_v2: MiaAgentV2


def build_application(settings: Settings | None = None) -> Application:
    """Build concrete dependencies without hiding behavior in a DI framework."""

    configured = settings or Settings()
    templates = OfficialTemplateRepository(configured.standards_root)
    web_tool = WebExtractionTool(loader=Crawl4AIPageLoader())
    resolver = ProductResolver(templates)
    website_workflow = WebsiteWorkflow(web_tool, resolver)
    search = DdgsSearchProvider()
    company_tool = CompanyDiscoveryTool(search)
    product_tool = ProductDiscoveryTool(search)

    chat_llm: ChatModel
    semantic_llm: SemanticModel
    if configured.openrouter_api_key is not None:
        api_key = configured.openrouter_api_key.get_secret_value()
        client = OpenRouterClient(api_key)
        chat_llm = ChatLLM(client, model=configured.conversation_model)
        semantic_llm = SemanticLLM(client, model=configured.semantic_model)
        agent_v2_model = OpenRouterModel(
            configured.agent_v2_model,
            provider=OpenRouterProvider(
                api_key=api_key,
                app_url="https://mia-dpp.vercel.app",
                app_title="MIA Digital Product Passport",
            ),
        )
    else:
        chat_llm = UnconfiguredChatLLM()
        semantic_llm = UnconfiguredSemanticLLM()
        agent_v2_model = None

    agent = MiaAgentWorkflow(templates, web_tool, resolver, chat_llm, semantic_llm)
    agent_v2 = MiaAgentV2(
        model=agent_v2_model,
        store=SQLiteThreadStore(configured.thread_store_path),
        company_tool=company_tool,
        product_tool=product_tool,
        web_tool=web_tool,
        mapping_tool=resolver,
        dpp_pipeline=DeterministicDppPipeline(templates),
    )
    return Application(
        settings=configured,
        templates=templates,
        web_tool=web_tool,
        resolver=resolver,
        website_workflow=website_workflow,
        chat_llm=chat_llm,
        semantic_llm=semantic_llm,
        agent_workflow=agent,
        agent_v2=agent_v2,
    )
