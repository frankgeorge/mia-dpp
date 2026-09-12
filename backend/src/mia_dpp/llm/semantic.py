"""Conservative semantic matching LLM role."""

from __future__ import annotations

import json
from typing import Protocol

from mia_dpp.domain.evidence import ProductKnowledgePackage
from mia_dpp.domain.mappings import CoverageReport, CoverageStatus, SemanticMatchDecision
from mia_dpp.domain.targets import RequirementKind
from mia_dpp.llm.client import LLMClient

SYSTEM_PROMPT = """You are MIA's semantic mapping assistant. Match manufacturer evidence
to official IDTA requirements conservatively. Use only evidenceId and requirementId values
present in the supplied JSON. A textual resemblance alone is insufficient: preserve
distinctions such as maximum versus nominal values, product name versus model, and different
voltage roles. Omit uncertain matches. Never invent values, requirements, semantic IDs, or
corroboration. Every result is a proposal requiring human approval. Do not map one evidence
record or one requirement more than once. Call the provided tool exactly once."""


class SemanticLLM:
    def __init__(self, client: LLMClient, *, model: str) -> None:
        self._client = client
        self._model = model

    @property
    def configured(self) -> bool:
        return True

    async def propose(
        self,
        package: ProductKnowledgePackage,
        coverage: CoverageReport,
    ) -> tuple[SemanticMatchDecision, ...]:
        unresolved_ids = {
            item.requirement_id
            for item in coverage.coverage
            if item.status
            in {CoverageStatus.CANDIDATE, CoverageStatus.AMBIGUOUS, CoverageStatus.MISSING}
        }
        requirements = [
            item
            for item in coverage.inventory.requirements
            if item.id in unresolved_ids
            and item.kind is RequirementKind.VALUE
            and item.semantic_id is not None
            and not item.wildcard
            and item.template_key == "digital_nameplate"
        ]
        if not requirements or not package.evidence:
            return ()

        evidence_payload = [
            {
                "id": item.id,
                "label": item.source_label or item.predicate,
                "value": item.value,
                "unit": item.unit,
                "context": (item.source_location.excerpt or "")[:240],
            }
            for item in package.evidence
        ]
        requirement_payload = [
            {
                "id": item.id,
                "name": item.id_short,
                "path": list(item.template_path),
                "description": (item.description or "")[:360],
                "valueType": item.value_type,
                "unit": item.unit,
                "required": item.required,
            }
            for item in requirements
        ]
        tool = {
            "type": "function",
            "function": {
                "name": "propose_semantic_matches",
                "description": "Propose review-only evidence to official requirement matches.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mappings": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "evidenceId": {"type": "string"},
                                    "requirementId": {"type": "string"},
                                    "reasoning": {"type": "string"},
                                },
                                "required": ["evidenceId", "requirementId", "reasoning"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["mappings"],
                    "additionalProperties": False,
                },
            },
        }
        arguments = await self._client.tool_call(
            model=self._model,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(
                        {"evidence": evidence_payload, "requirements": requirement_payload},
                        ensure_ascii=False,
                    ),
                }
            ],
            tool=tool,
            tool_name="propose_semantic_matches",
            max_tokens=1800,
        )
        return self._validated(arguments, package, {item.id for item in requirements})

    @staticmethod
    def _validated(
        arguments: dict[str, object],
        package: ProductKnowledgePackage,
        valid_requirements: set[str],
    ) -> tuple[SemanticMatchDecision, ...]:
        raw_mappings = arguments.get("mappings", [])
        if not isinstance(raw_mappings, list):
            raise ValueError("semantic mapping tool returned a non-list mappings value")
        valid_evidence = {item.id for item in package.evidence}
        seen_evidence: set[str] = set()
        seen_requirements: set[str] = set()
        result: list[SemanticMatchDecision] = []
        for raw in raw_mappings:
            try:
                decision = SemanticMatchDecision.model_validate(raw)
            except ValueError:
                continue
            if (
                decision.evidence_id not in valid_evidence
                or decision.requirement_id not in valid_requirements
                or decision.evidence_id in seen_evidence
                or decision.requirement_id in seen_requirements
            ):
                continue
            seen_evidence.add(decision.evidence_id)
            seen_requirements.add(decision.requirement_id)
            result.append(decision)
        return tuple(result)


class SemanticModel(Protocol):
    """Provider-neutral semantic reasoning role used by the agent."""

    @property
    def configured(self) -> bool: ...

    async def propose(
        self,
        package: ProductKnowledgePackage,
        coverage: CoverageReport,
    ) -> tuple[SemanticMatchDecision, ...]: ...


class UnconfiguredSemanticLLM:
    @property
    def configured(self) -> bool:
        return False

    async def propose(
        self,
        package: ProductKnowledgePackage,
        coverage: CoverageReport,
    ) -> tuple[SemanticMatchDecision, ...]:
        return ()
