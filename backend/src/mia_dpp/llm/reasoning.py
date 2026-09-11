"""Composite reasoning capability used by the current agent workflow."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from mia_dpp.domain.contracts import (
    ChatMessage,
    ConversationDecision,
    CoverageReport,
    ProductKnowledgePackage,
    SemanticMatchDecision,
)
from mia_dpp.integrations.openrouter import OpenRouterClient
from mia_dpp.llm.conversation import ConversationLLM
from mia_dpp.llm.semantic import SemanticLLM


class ReasoningService(Protocol):
    @property
    def configured(self) -> bool: ...

    async def converse(self, messages: Sequence[ChatMessage]) -> ConversationDecision: ...

    async def propose_semantic_matches(
        self,
        package: ProductKnowledgePackage,
        coverage: CoverageReport,
    ) -> tuple[SemanticMatchDecision, ...]: ...


class UnconfiguredReasoningService:
    @property
    def configured(self) -> bool:
        return False

    async def converse(self, messages: Sequence[ChatMessage]) -> ConversationDecision:
        return ConversationDecision(
            intent="chat",
            reply=(
                "MIA can import a manufacturer product page, retain its evidence, compare "
                "it with official IDTA requirements, and ask you to review semantic matches. "
                "Configure OPENROUTER_API_KEY to enable conversational and semantic reasoning."
            ),
        )

    async def propose_semantic_matches(
        self,
        package: ProductKnowledgePackage,
        coverage: CoverageReport,
    ) -> tuple[SemanticMatchDecision, ...]:
        return ()


class OpenRouterReasoningService:
    """Compatibility facade composing two provider-neutral LLM roles."""

    def __init__(
        self,
        api_key: str,
        *,
        conversation_model: str,
        semantic_model: str,
        timeout: float = 90.0,
    ) -> None:
        client = OpenRouterClient(api_key, timeout=timeout)
        self._conversation = ConversationLLM(client, model=conversation_model)
        self._semantic = SemanticLLM(client, model=semantic_model)

    @property
    def configured(self) -> bool:
        return True

    async def converse(self, messages: Sequence[ChatMessage]) -> ConversationDecision:
        return await self._conversation.decide(messages)

    async def propose_semantic_matches(
        self,
        package: ProductKnowledgePackage,
        coverage: CoverageReport,
    ) -> tuple[SemanticMatchDecision, ...]:
        return await self._semantic.propose(package, coverage)
