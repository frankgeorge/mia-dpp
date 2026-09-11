"""OpenRouter transport implementing MIA's structured LLM client boundary."""

from __future__ import annotations

import json
from typing import Any, cast

import httpx

from mia_dpp.llm.conversation import ConversationLLM
from mia_dpp.llm.reasoning import CompositeReasoningService
from mia_dpp.llm.semantic import SemanticLLM

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterClient:
    def __init__(self, api_key: str, *, timeout: float = 90.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    async def tool_call(
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


class OpenRouterReasoningService(CompositeReasoningService):
    """Assemble MIA's LLM roles over the OpenRouter transport."""

    def __init__(
        self,
        api_key: str,
        *,
        conversation_model: str,
        semantic_model: str,
        timeout: float = 90.0,
    ) -> None:
        client = OpenRouterClient(api_key, timeout=timeout)
        super().__init__(
            ConversationLLM(client, model=conversation_model),
            SemanticLLM(client, model=semantic_model),
        )
