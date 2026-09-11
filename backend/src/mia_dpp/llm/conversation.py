"""Conversational intake LLM role."""

from __future__ import annotations

from collections.abc import Sequence

from mia_dpp.domain.contracts import ChatMessage, ConversationDecision
from mia_dpp.llm.client import LLMClient

SYSTEM_PROMPT = """You are MIA, an assistant for building evidence-backed Digital Product
Passports and Asset Administration Shells. Explain that MIA can ingest a direct public
manufacturer product-page URL, retain source provenance, compare evidence with official
IDTA templates, and request human review for uncertain semantic mappings. Ask concise
questions that move the user toward a direct product URL or a precise manual description.
Never claim that an AAS is complete before deterministic validation. Choose ingest_website
only when the user supplied a direct http(s) URL; otherwise choose chat. Call the provided
tool exactly once."""


class ConversationLLM:
    def __init__(self, client: LLMClient, *, model: str) -> None:
        self._client = client
        self._model = model

    async def decide(self, messages: Sequence[ChatMessage]) -> ConversationDecision:
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
        arguments = await self._client.tool_call(
            model=self._model,
            system=SYSTEM_PROMPT,
            messages=[item.model_dump() for item in messages],
            tool=tool,
            tool_name="respond_to_user",
            max_tokens=600,
        )
        return ConversationDecision.model_validate(arguments)
