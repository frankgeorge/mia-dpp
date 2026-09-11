"""Explicit construction of the MIA application and its external integrations."""

from __future__ import annotations

from dataclasses import dataclass

from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.agent.graph import MiaAgentWorkflow
from mia_dpp.config import Settings
from mia_dpp.llm.reasoning import (
    OpenRouterReasoningService,
    ReasoningService,
    UnconfiguredReasoningService,
)
from mia_dpp.sources.website import WebsiteIngestionService


@dataclass(frozen=True)
class Application:
    settings: Settings
    templates: OfficialTemplateRepository
    website_ingestion: WebsiteIngestionService
    reasoning: ReasoningService
    agent_workflow: MiaAgentWorkflow


def build_application(settings: Settings | None = None) -> Application:
    """Assemble MIA with simple explicit dependency construction."""

    configured = settings or Settings()
    templates = OfficialTemplateRepository(configured.standards_root)
    website_ingestion = WebsiteIngestionService(templates)
    reasoning: ReasoningService
    if configured.openrouter_api_key is not None:
        reasoning = OpenRouterReasoningService(
            configured.openrouter_api_key.get_secret_value(),
            conversation_model=configured.conversation_model,
            semantic_model=configured.semantic_model,
        )
    else:
        reasoning = UnconfiguredReasoningService()
    return Application(
        settings=configured,
        templates=templates,
        website_ingestion=website_ingestion,
        reasoning=reasoning,
        agent_workflow=MiaAgentWorkflow(templates, website_ingestion, reasoning),
    )
