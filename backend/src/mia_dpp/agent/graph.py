"""Readable LangGraph topology and public resumable workflow."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.agent.nodes.complete import CompleteNodes
from mia_dpp.agent.nodes.intake import IntakeNodes
from mia_dpp.agent.nodes.resolve import ResolveNodes
from mia_dpp.agent.nodes.review import ReviewNodes
from mia_dpp.agent.state import AgentState
from mia_dpp.api.schemas import (
    AgentMessageRequest,
    AgentResponse,
    AgentReviewRequest,
    WebsiteIngestResponse,
)
from mia_dpp.domain.mappings import SemanticReviewItem
from mia_dpp.domain.workflow import AgentRunStatus
from mia_dpp.llm.conversation import ChatMessage
from mia_dpp.llm.reasoning import ReasoningService
from mia_dpp.resolution.coverage import CoverageAnalyzer
from mia_dpp.sources.website import WebsiteIngestionService
from mia_dpp.tools.semantic import SemanticTool
from mia_dpp.tools.source import SourceTool

_URL = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)


class MiaAgentWorkflow(IntakeNodes, ResolveNodes, ReviewNodes, CompleteNodes):
    def __init__(
        self,
        repository: OfficialTemplateRepository,
        website_ingestion: WebsiteIngestionService,
        reasoning: ReasoningService,
    ) -> None:
        self._repository = repository
        self._source_tool = SourceTool(website_ingestion)
        self._reasoning = reasoning
        self._semantic_tool = SemanticTool(reasoning)
        self._coverage_analyzer = CoverageAnalyzer()
        self._pending_chat: dict[str, list[ChatMessage]] = {}
        builder = StateGraph(AgentState)
        builder.add_node("intake", self._intake)
        builder.add_node("website_ingestion", self._ingest_website)
        builder.add_node("semantic_resolution", self._resolve_semantics)
        builder.add_node("human_review", self._human_review)
        builder.add_edge(START, "intake")
        builder.add_conditional_edges(
            "intake",
            self._after_intake,
            {"website": "website_ingestion", "done": END},
        )
        builder.add_edge("website_ingestion", "semantic_resolution")
        builder.add_conditional_edges(
            "semantic_resolution",
            self._after_semantics,
            {"review": "human_review", "completion": "assess_completion"},
        )
        builder.add_edge("human_review", "assess_completion")
        builder.add_node("assess_completion", self._assess_completion)
        builder.add_node("human_completion", self._human_completion)
        builder.add_node("optional_choice", self._optional_choice)
        builder.add_conditional_edges(
            "assess_completion",
            self._after_completion_assessment,
            {
                "input": "human_completion",
                "optional": "optional_choice",
                "done": END,
            },
        )
        builder.add_edge("human_completion", "assess_completion")
        builder.add_conditional_edges(
            "optional_choice",
            self._after_optional_choice,
            {"input": "human_completion", "done": END},
        )
        self._graph = builder.compile(checkpointer=InMemorySaver())

    async def message(self, request: AgentMessageRequest) -> AgentResponse:
        thread_id = request.thread_id or f"thread-{uuid.uuid4().hex}"
        if request.thread_id:
            snapshot = await self._graph.aget_state(self._config(thread_id))
            if snapshot.next:
                if "human_review" in snapshot.next and snapshot.values.get("review_items"):
                    return await self._message_during_review(thread_id, request, snapshot.values)
                if "human_completion" in snapshot.next:
                    return await self._resume_with_message(
                        thread_id,
                        {"answer": request.message},
                    )
                if "optional_choice" in snapshot.next:
                    return await self._resume_with_message(
                        thread_id,
                        {"choice": request.message},
                    )
        state: AgentState = {
            "messages": [{"role": "user", "content": request.message}],
            "user_message": request.message,
            "graph_history": [item.model_dump(mode="json") for item in request.graph],
            "configured": self._reasoning.configured,
            "website_result": None,
            "review_items": [],
            "asked_requirement_ids": [],
            "optional_enabled": False,
            "status": "completed",
        }
        result = await self._graph.ainvoke(state, self._config(thread_id))
        return self._response(thread_id, result)

    async def _resume_with_message(
        self,
        thread_id: str,
        payload: dict[str, str],
    ) -> AgentResponse:
        result = await self._graph.ainvoke(
            Command(resume=payload),
            self._config(thread_id),
        )
        return self._response(thread_id, result)

    async def _message_during_review(
        self,
        thread_id: str,
        request: AgentMessageRequest,
        state: dict[str, Any],
    ) -> AgentResponse:
        """Keep conversation available without consuming the review interrupt."""

        stored = self._pending_chat.setdefault(thread_id, [])
        history = tuple(
            [ChatMessage.model_validate(item) for item in state.get("messages", [])]
            + stored
            + [ChatMessage(role="user", content=request.message)]
        )
        decision = await self._reasoning.converse(history)
        stored.extend(
            [
                ChatMessage(role="user", content=request.message),
                ChatMessage(role="assistant", content=decision.reply),
            ]
        )
        response_state = dict(state)
        response_state["reply"] = decision.reply
        response_state["status"] = "awaiting_review"
        return self._response(thread_id, response_state)

    async def review(self, request: AgentReviewRequest) -> AgentResponse:
        command: Command[Any] = Command(resume=request.model_dump(mode="json"))
        result = await self._graph.ainvoke(
            command,
            self._config(request.thread_id),
        )
        self._pending_chat.pop(request.thread_id, None)
        return self._response(request.thread_id, result)

    def _response(self, thread_id: str, state: dict[str, Any]) -> AgentResponse:
        website = state.get("website_result")
        items = state.get("review_items", [])
        status = AgentRunStatus(state.get("status", "completed"))
        return AgentResponse(
            thread_id=thread_id,
            reply=state.get("reply", "MIA is ready."),
            status=status,
            mode="agent" if state.get("configured") else "configuration_required",
            website_result=(
                WebsiteIngestResponse.model_validate(website) if website is not None else None
            ),
            review_items=tuple(SemanticReviewItem.model_validate(item) for item in items),
        )

    @staticmethod
    def _display_value(value: object, unit: str | None) -> str:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return f"{text} {unit}" if unit and not str(text).endswith(unit) else str(text)

    @staticmethod
    def _config(thread_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": thread_id}}
