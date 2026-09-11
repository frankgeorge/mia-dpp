"""Composite reasoning capability used by the current agent workflow."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from mia_dpp.domain.evidence import ProductKnowledgePackage
from mia_dpp.domain.mappings import CoverageReport, SemanticMatchDecision
from mia_dpp.llm.conversation import ChatMessage, ConversationDecision, ConversationLLM
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


class CompositeReasoningService:
    """Combine conversation and semantic roles behind the agent boundary."""

    def __init__(
        self,
        conversation: ConversationLLM,
        semantic: SemanticLLM,
    ) -> None:
        self._conversation = conversation
        self._semantic = semantic

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
