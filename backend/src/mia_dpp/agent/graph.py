"""Small LangGraph lifecycle around MIA's autonomous PydanticAI brain."""

from __future__ import annotations

import asyncio
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.sqlite import SqliteStore
from langgraph.types import Command, interrupt
from pydantic_ai.messages import ModelMessagesTypeAdapter

from mia_dpp.agent.brain import AutonomousAgent
from mia_dpp.agent.models import (
    AgentRequest,
    AgentResponse,
    AgentReviewRequest,
    AgentStatus,
    AgentValueRequest,
    HumanRequestKind,
    MiaState,
    ProductStatus,
)
from mia_dpp.tools.mapping.review import MappingReviewService
from mia_dpp.workspace.models import ArtifactKind
from mia_dpp.workspace.store import WorkspaceStore


class LifecycleState(TypedDict, total=False):
    """Checkpointed job state plus PydanticAI history and the current API turn."""

    job: dict[str, Any]
    model_history_json: str
    user_message: str
    reply: str
    decision_summary: str
    trace_offset: int


class MiaAgent:
    """Own thread lifetime while delegating every autonomous choice to PydanticAI.

    LangGraph checkpoints job state and model history, interrupts for human
    authority, and resumes the same thread. PydanticAI alone selects tools.
    """

    def __init__(
        self,
        *,
        brain: AutonomousAgent,
        mapping_review: MappingReviewService,
        workspace: WorkspaceStore,
        database_path: Path,
    ) -> None:
        self._brain = brain
        self._mapping_review = mapping_review
        self._workspace = workspace
        self._database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_connection = sqlite3.connect(database_path, check_same_thread=False)
        memory_path = database_path.with_name(database_path.stem + "-memory.sqlite3")
        memory_connection = sqlite3.connect(memory_path, check_same_thread=False)
        self._checkpointer = SqliteSaver(checkpoint_connection)
        self._memory = SqliteStore(memory_connection)
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mia-brain")
        self._checkpointer.setup()
        self._memory.setup()
        builder = StateGraph(LifecycleState)
        builder.add_node("autonomous_agent", self._agent_node)  # type: ignore[call-overload]
        builder.add_node("human_interrupt", self._human_interrupt)  # type: ignore[call-overload]
        builder.add_edge(START, "autonomous_agent")
        builder.add_conditional_edges(
            "autonomous_agent",
            self._after_agent,
            {"human": "human_interrupt", "done": END},
        )
        builder.add_edge("human_interrupt", END)
        self._builder = builder
        self._graph = builder.compile(checkpointer=self._checkpointer, store=self._memory)

    async def message(self, request: AgentRequest) -> AgentResponse:
        """Run one checkpointed user turn through the autonomous PydanticAI loop."""

        thread_id = request.thread_id or f"thread-{uuid.uuid4().hex}"
        snapshot = self._graph.get_state(self._config(thread_id))
        if snapshot.next:
            state = MiaState.model_validate(snapshot.values["job"])
            return self._response(
                state,
                reply="MIA is waiting for the requested human input before continuing.",
                decision_summary="A trusted human action is required.",
                trace_offset=len(state.trace),
            )
        graph_input = (
            {"user_message": request.message}
            if snapshot.values
            else self.initial_input(thread_id, request.message)
        )
        values = self._graph.invoke(graph_input, self._config(thread_id))
        return self._response_from_values(thread_id, values)

    async def review(self, request: AgentReviewRequest) -> AgentResponse:
        """Resume a mapping-review interrupt with trusted API decisions."""

        return self._resume(request.thread_id, request.model_dump(mode="json"))

    async def provide_value(self, request: AgentValueRequest) -> AgentResponse:
        """Resume a missing-value interrupt without exposing human authority to the model."""

        return self._resume(request.thread_id, request.model_dump(mode="json"))

    def _resume(self, thread_id: str, payload: dict[str, Any]) -> AgentResponse:
        values = self._graph.invoke(Command(resume=payload), self._config(thread_id))
        return self._response_from_values(thread_id, values)

    def _agent_node(self, values: LifecycleState) -> LifecycleState:
        state = MiaState.model_validate(values["job"])
        message = values.get("user_message", "Continue the current MIA task.")
        if not state.user_goal:
            state.user_goal = message
        history = ModelMessagesTypeAdapter.validate_json(values.get("model_history_json", "[]"))
        output, messages, trace_offset = self._executor.submit(
            asyncio.run,
            self._brain.run(message, state, history),
        ).result()
        self._persist_trace(state, trace_offset)
        self._persist_snapshot(state, output.decision_summary)
        return {
            "job": state.model_dump(mode="json"),
            "model_history_json": ModelMessagesTypeAdapter.dump_json(messages).decode(),
            "reply": output.reply,
            "decision_summary": output.decision_summary,
            "trace_offset": trace_offset,
            "user_message": "Continue after the trusted human action.",
        }

    def _human_interrupt(self, values: LifecycleState) -> LifecycleState:
        state = MiaState.model_validate(values["job"])
        request = state.pending_human_request
        if request is None:
            return values
        payload = interrupt(request.model_dump(mode="json"))
        if request.kind is HumanRequestKind.MAPPING_REVIEW:
            self._apply_reviews(state, payload)
        else:
            self._apply_human_value(state, payload)
        state.pending_human_request = None
        state.add_event(
            "human.input_received",
            "Trusted human input was applied to the paused workflow.",
            product_id=request.product_id,
        )
        self._persist_trace(state, len(state.trace) - 1)
        self._persist_snapshot(state, "Trusted human input applied.")
        return {
            **values,
            "job": state.model_dump(mode="json"),
            "reply": "Human input saved. MIA can continue on the next message.",
            "decision_summary": "Trusted human input was deterministically applied.",
        }

    def _apply_reviews(self, state: MiaState, payload: object) -> None:
        request = AgentReviewRequest.model_validate(payload)
        work = state.products.get(request.product_id)
        if work is None or work.resolution is None:
            raise ValueError("unknown or unresolved product")
        pending = {item.id: item for item in work.pending_reviews}
        for decision in request.decisions:
            item = pending.get(decision.review_id)
            if item is None:
                raise ValueError(f"review is not pending: {decision.review_id}")
            work.resolution, reviewed = self._mapping_review.decide(
                work.resolution,
                item,
                decision=decision.decision,
                thread_id=state.thread_id,
                corrected_requirement_id=decision.corrected_requirement_id,
                corrected_value=decision.corrected_value,
            )
            artifact = self._workspace.write_json(
                state.thread_id,
                ArtifactKind.REVIEW,
                "mapping-review.json",
                decision.model_dump(mode="json"),
                created_by="human",
                product_id=request.product_id,
                derived_from=(reviewed.mapping.evidence_id,),
            )
            work.artifact_ids = (*work.artifact_ids, artifact.id)
            pending.pop(decision.review_id)
        work.pending_reviews = tuple(pending.values())
        work.status = ProductStatus.AWAITING_REVIEW if pending else ProductStatus.IN_PROGRESS
        state.products[request.product_id] = work
        state.status = AgentStatus.AWAITING_REVIEW if pending else AgentStatus.RUNNING

    def _apply_human_value(self, state: MiaState, payload: object) -> None:
        request = AgentValueRequest.model_validate(payload)
        work = state.products.get(request.product_id)
        if work is None or work.resolution is None:
            raise ValueError("unknown or unresolved product")
        work.resolution = self._mapping_review.record_human_value(
            work.resolution,
            requirement_id=request.requirement_id,
            value=request.value,
            thread_id=state.thread_id,
        )
        artifact = self._workspace.write_json(
            state.thread_id,
            ArtifactKind.REVIEW,
            "human-evidence.json",
            request.model_dump(mode="json"),
            created_by="human",
            product_id=request.product_id,
        )
        work.artifact_ids = (*work.artifact_ids, artifact.id)
        state.products[request.product_id] = work
        state.status = AgentStatus.RUNNING

    @staticmethod
    def _after_agent(values: LifecycleState) -> Literal["human", "done"]:
        state = MiaState.model_validate(values["job"])
        return "human" if state.pending_human_request is not None else "done"

    def _response_from_values(self, thread_id: str, values: dict[str, Any]) -> AgentResponse:
        state = MiaState.model_validate(values["job"])
        if state.thread_id != thread_id:
            raise ValueError("checkpoint thread mismatch")
        return self._response(
            state,
            reply=values.get("reply", "MIA is ready."),
            decision_summary=values.get("decision_summary", "The workflow state was restored."),
            trace_offset=int(values.get("trace_offset", len(state.trace))),
        )

    def _response(
        self,
        state: MiaState,
        *,
        reply: str,
        decision_summary: str,
        trace_offset: int,
    ) -> AgentResponse:
        current = state.products.get(state.current_product_id) if state.current_product_id else None
        return AgentResponse(
            thread_id=state.thread_id,
            reply=reply,
            status=state.status,
            decision_summary=decision_summary,
            company_candidates=state.company_candidates,
            selected_company=state.selected_company,
            product_candidates=state.product_candidates,
            selected_product_ids=state.selected_product_ids,
            current_product=current,
            pending_human_request=state.pending_human_request,
            trace_events=state.trace[trace_offset:],
            artifact_count=len(self._workspace.list_artifacts(state.thread_id)),
        )

    def _persist_trace(self, state: MiaState, offset: int) -> None:
        for event in state.trace[offset:]:
            self._workspace.write_json(
                state.thread_id,
                ArtifactKind.TRACE,
                "event.json",
                event.model_dump(mode="json"),
                created_by="langgraph",
                product_id=event.product_id,
            )

    def _persist_snapshot(self, state: MiaState, decision: str) -> None:
        current = state.products.get(state.current_product_id) if state.current_product_id else None
        resolution = current.resolution if current is not None else None
        statistics = resolution.coverage_report.statistics if resolution is not None else None
        self._workspace.write_json(
            state.thread_id,
            ArtifactKind.TRACE,
            "state-snapshot.json",
            {
                "status": state.status,
                "decisionSummary": decision,
                "selectedCompany": state.selected_company.name if state.selected_company else None,
                "currentProductId": state.current_product_id,
                "queuedProducts": list(state.product_queue),
                "sourceCount": len(current.extractions) if current else 0,
                "evidenceCount": len(resolution.evidence) if resolution else 0,
                "mappedCount": len(resolution.mapping_result.mapped) if resolution else 0,
                "unmatchedCount": (
                    len(resolution.mapping_result.unmatched_evidence_ids) if resolution else 0
                ),
                "missingMandatory": statistics.required_missing if statistics else 0,
                "pendingReviews": len(current.pending_reviews) if current else 0,
                "artifactCount": len(self._workspace.list_artifacts(state.thread_id)),
            },
            created_by="langgraph",
            product_id=state.current_product_id,
        )

    @staticmethod
    def initial_input(thread_id: str, message: str) -> LifecycleState:
        state = MiaState(thread_id=thread_id, user_goal=message)
        return {
            "job": state.model_dump(mode="json"),
            "model_history_json": "[]",
            "user_message": message,
        }

    @staticmethod
    def _config(thread_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": thread_id}}
