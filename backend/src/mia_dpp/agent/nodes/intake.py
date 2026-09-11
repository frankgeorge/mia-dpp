# mypy: disable-error-code="attr-defined"
"""Conversation intent and website acquisition nodes."""

from __future__ import annotations

import re
from typing import Literal

from mia_dpp.agent.state import AgentState
from mia_dpp.domain.contracts import (
    ChatMessage,
    GraphEntry,
    WebsiteIngestRequest,
)

_URL = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)


class IntakeNodes:
    async def _intake(self, state: AgentState) -> AgentState:
        message = state["user_message"]
        match = _URL.search(message)
        if match:
            url = match.group(0).rstrip(".,;:!?)']")
            return {
                "route": "website",
                "website_url": url,
                "reply": "I found a product URL and will build its evidence ledger now.",
            }

        history = tuple(ChatMessage.model_validate(item) for item in state.get("messages", []))
        decision = await self._reasoning.converse(history)
        if decision.intent == "ingest_website" and decision.url:
            return {
                "route": "website",
                "website_url": decision.url,
                "reply": decision.reply,
            }
        return {
            "route": "chat",
            "reply": decision.reply,
            "messages": [{"role": "assistant", "content": decision.reply}],
            "status": "completed",
        }

    async def _after_intake(self, state: AgentState) -> Literal["website", "done"]:
        return "website" if state["route"] == "website" else "done"

    async def _ingest_website(self, state: AgentState) -> AgentState:
        history = tuple(GraphEntry.model_validate(item) for item in state.get("graph_history", []))
        result = await self._source_tool.ingest(
            WebsiteIngestRequest(url=state["website_url"], graph=history)
        )
        return {"website_result": result.model_dump(mode="json")}
