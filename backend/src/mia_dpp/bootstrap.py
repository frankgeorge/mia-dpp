"""Composition root: connect MIA roles, tools, core logic, and integrations."""

from __future__ import annotations

from dataclasses import dataclass

from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.agent.graph import MiaAgentWorkflow
from mia_dpp.config import Settings
from mia_dpp.integrations.crawl4ai import Crawl4AIPageLoader
from mia_dpp.integrations.openrouter import OpenRouterClient
from mia_dpp.llm.chat import ChatLLM, ChatModel, UnconfiguredChatLLM
from mia_dpp.llm.semantic import SemanticLLM, SemanticModel, UnconfiguredSemanticLLM
from mia_dpp.resolution.resolver import ProductResolver, WebsiteWorkflow
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


def build_application(settings: Settings | None = None) -> Application:
    """Build concrete dependencies without hiding behavior in a DI framework."""

    configured = settings or Settings()
    templates = OfficialTemplateRepository(configured.standards_root)
    web_tool = WebExtractionTool(loader=Crawl4AIPageLoader())
    resolver = ProductResolver(templates)
    website_workflow = WebsiteWorkflow(web_tool, resolver)

    chat_llm: ChatModel
    semantic_llm: SemanticModel
    if configured.openrouter_api_key is not None:
        client = OpenRouterClient(configured.openrouter_api_key.get_secret_value())
        chat_llm = ChatLLM(client, model=configured.conversation_model)
        semantic_llm = SemanticLLM(client, model=configured.semantic_model)
    else:
        chat_llm = UnconfiguredChatLLM()
        semantic_llm = UnconfiguredSemanticLLM()

    agent = MiaAgentWorkflow(templates, web_tool, resolver, chat_llm, semantic_llm)
    return Application(
        settings=configured,
        templates=templates,
        web_tool=web_tool,
        resolver=resolver,
        website_workflow=website_workflow,
        chat_llm=chat_llm,
        semantic_llm=semantic_llm,
        agent_workflow=agent,
    )
