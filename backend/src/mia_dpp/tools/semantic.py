"""Agent-facing semantic proposal capability."""

from mia_dpp.domain.evidence import ProductKnowledgePackage
from mia_dpp.domain.mappings import CoverageReport, SemanticMatchDecision
from mia_dpp.llm.reasoning import ReasoningService


class SemanticTool:
    def __init__(self, reasoning: ReasoningService) -> None:
        self._reasoning = reasoning

    @property
    def configured(self) -> bool:
        return self._reasoning.configured

    async def propose(
        self,
        package: ProductKnowledgePackage,
        coverage: CoverageReport,
    ) -> tuple[SemanticMatchDecision, ...]:
        return await self._reasoning.propose_semantic_matches(package, coverage)
