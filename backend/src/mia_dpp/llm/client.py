"""Provider-neutral structured LLM call boundary."""

from __future__ import annotations

from typing import Any, Protocol


class LLMClient(Protocol):
    """Execute one forced structured tool call."""

    async def tool_call(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, str]],
        tool: dict[str, Any],
        tool_name: str,
        max_tokens: int,
    ) -> dict[str, object]: ...
