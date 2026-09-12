"""The conversational LLM role that talks to MIA users."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol

from pydantic import Field, model_validator

from mia_dpp.domain.base import WireModel
from mia_dpp.llm.client import LLMClient


class ChatMessage(WireModel):
    role: Literal["user", "assistant"]
    content: str


class ConversationDecision(WireModel):
    """Typed result of the conversational intake model."""

    intent: Literal["chat", "ingest_website"]
    reply: str = Field(min_length=1)
    url: str | None = None

    @model_validator(mode="after")
    def website_intent_has_url(self) -> ConversationDecision:
        if self.intent == "ingest_website" and not self.url:
            raise ValueError("website ingestion intent requires a URL")
        if self.intent == "chat" and self.url is not None:
            raise ValueError("chat intent cannot include a URL")
        return self


SYSTEM_PROMPT = """You are MIA, an assistant for building evidence-backed Digital Product
Passports and Asset Administration Shells. Explain that MIA can ingest a direct public
manufacturer product-page URL, retain source provenance, compare evidence with official
IDTA templates, and request human review for uncertain semantic mappings. Ask concise
questions that move the user toward a direct product URL or a precise manual description.
Never claim that an AAS is complete before deterministic validation. Choose ingest_website
only when the user supplied a direct http(s) URL; otherwise choose chat. Call the provided
tool exactly once."""


class ChatLLM:
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

    @property
    def configured(self) -> bool:
        return True


class ChatModel(Protocol):
    @property
    def configured(self) -> bool: ...

    async def decide(self, messages: Sequence[ChatMessage]) -> ConversationDecision: ...


class UnconfiguredChatLLM:
    @property
    def configured(self) -> bool:
        return False

    async def decide(self, messages: Sequence[ChatMessage]) -> ConversationDecision:
        return ConversationDecision(
            intent="chat",
            reply=(
                "MIA can import a manufacturer product page, retain its evidence, compare "
                "it with official IDTA requirements, and ask you to review semantic matches. "
                "Configure OPENROUTER_API_KEY to enable conversational and semantic reasoning."
            ),
        )
