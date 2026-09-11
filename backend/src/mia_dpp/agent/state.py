"""State remembered by the resumable MIA LangGraph workflow."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict


class AgentState(TypedDict, total=False):
    """LangGraph-owned state; API/domain objects cross the boundary as JSON."""

    messages: Annotated[list[dict[str, str]], operator.add]
    user_message: str
    route: Literal["chat", "website"]
    reply: str
    configured: bool
    graph_history: list[dict[str, Any]]
    website_url: str
    website_result: dict[str, Any] | None
    review_items: list[dict[str, Any]]
    status: Literal[
        "completed",
        "awaiting_review",
        "awaiting_input",
        "awaiting_optional_choice",
    ]
    active_requirement_id: str
    completion_phase: Literal["mandatory", "optional"]
    asked_requirement_ids: list[str]
    optional_enabled: bool
