"""LLM boundary for conversational intake and unresolved semantic matching.

The model can choose only identifiers supplied by MIA. Official template
metadata, confidence arithmetic, approval, compilation and validation remain
owned by deterministic Python.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Protocol, cast

import httpx

from mia_dpp.models import (
    ChatMessage,
    ConversationDecision,
    CoverageReport,
    CoverageStatus,
    ProductKnowledgePackage,
    RequirementKind,
    SemanticMatchDecision,
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class ReasoningService(Protocol):
    """Provider-neutral reasoning used by the LangGraph application layer."""

    @property
    def configured(self) -> bool: ...

    async def converse(self, messages: Sequence[ChatMessage]) -> ConversationDecision: ...

    async def propose_semantic_matches(
        self,
        package: ProductKnowledgePackage,
        coverage: CoverageReport,
    ) -> tuple[SemanticMatchDecision, ...]: ...


class UnconfiguredReasoningService:
    """Safe local behavior when no external model credential is configured."""

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
    """Narrow OpenRouter adapter returning validated MIA domain objects."""

    def __init__(
        self,
        api_key: str,
        *,
        conversation_model: str,
        semantic_model: str,
        timeout: float = 90.0,
    ) -> None:
        self._api_key = api_key
        self._conversation_model = conversation_model
        self._semantic_model = semantic_model
        self._timeout = timeout

    @property
    def configured(self) -> bool:
        return True

    async def converse(self, messages: Sequence[ChatMessage]) -> ConversationDecision:
        tool = {
            "type": "function",
            "function": {
                "name": "respond_to_user",
                "description": "Respond to the user and identify whether a product URL was given.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "intent": {"type": "string", "enum": ["chat", "ingest_website"]},
                        "reply": {"type": "string"},
                        "url": {"type": ["string", "null"]},
                    },
                    "required": ["intent", "reply", "url"],
                    "additionalProperties": False,
                },
            },
        }
        system = """You are MIA, an assistant for building evidence-backed Digital Product
Passports and Asset Administration Shells. Explain that MIA can ingest a direct public
manufacturer product-page URL, retain source provenance, compare evidence with official
IDTA templates, and request human review for uncertain semantic mappings. Ask concise
questions that move the user toward a direct product URL or a precise manual description.
Never claim that an AAS is complete before deterministic validation. Choose ingest_website
only when the user supplied a direct http(s) URL; otherwise choose chat. Call the provided
tool exactly once."""
        arguments = await self._tool_call(
            model=self._conversation_model,
            system=system,
            messages=[item.model_dump() for item in messages],
            tool=tool,
            tool_name="respond_to_user",
            max_tokens=600,
        )
        return ConversationDecision.model_validate(arguments)

    async def propose_semantic_matches(
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
            # The current compiler produces Digital Nameplate. Other selected templates
            # remain visible in Coverage until multi-submodel compilation is implemented.
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
        context = json.dumps(
            {"evidence": evidence_payload, "requirements": requirement_payload},
            ensure_ascii=False,
        )
        system = """You are MIA's semantic mapping assistant. Match manufacturer evidence
to official IDTA requirements conservatively. Use only evidenceId and requirementId values
present in the supplied JSON. A textual resemblance alone is insufficient: preserve
distinctions such as maximum versus nominal values, product name versus model, and different
voltage roles. Omit uncertain matches. Never invent values, requirements, semantic IDs, or
corroboration. Every result is a proposal requiring human approval. Do not map one evidence
record or one requirement more than once. Call the provided tool exactly once."""
        arguments = await self._tool_call(
            model=self._semantic_model,
            system=system,
            messages=[{"role": "user", "content": context}],
            tool=tool,
            tool_name="propose_semantic_matches",
            max_tokens=1800,
        )

        valid_evidence = {item.id for item in package.evidence}
        valid_requirements = {item.id for item in requirements}
        seen_evidence: set[str] = set()
        seen_requirements: set[str] = set()
        result: list[SemanticMatchDecision] = []
        raw_mappings = arguments.get("mappings", [])
        if not isinstance(raw_mappings, list):
            raise ValueError("semantic mapping tool returned a non-list mappings value")
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

    async def _tool_call(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, str]],
        tool: dict[str, Any],
        tool_name: str,
        max_tokens: int,
    ) -> dict[str, object]:
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "tools": [tool],
            "tool_choice": {"type": "function", "function": {"name": tool_name}},
            "messages": [{"role": "system", "content": system}, *messages],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "HTTP-Referer": "https://mia-dpp.vercel.app",
            "X-Title": "MIA Digital Product Passport",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
            response.raise_for_status()
        message = response.json()["choices"][0]["message"]
        calls = message.get("tool_calls") or []
        call = next(
            (item for item in calls if (item.get("function") or {}).get("name") == tool_name),
            None,
        )
        if call is None:
            raise ValueError(f"model did not call required tool {tool_name}")
        decoded = json.loads(call["function"]["arguments"])
        if not isinstance(decoded, dict):
            raise ValueError(f"tool {tool_name} returned a non-object payload")
        return cast(dict[str, object], decoded)
