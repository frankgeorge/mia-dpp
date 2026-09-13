"""Trusted server-side persistence for PydanticAI history and MIA workflow state."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from mia_dpp.agent.v2.models import MiaState


@dataclass(frozen=True)
class ThreadSnapshot:
    """Workflow state and model history loaded together for one thread ID."""

    state: MiaState
    messages: list[ModelMessage]


class ThreadStore(Protocol):
    """Persistence boundary for trusted Agent V2 threads.

    Implementations store workflow state and PydanticAI conversation history as
    separate values, while retrieving both through the same thread identifier.
    """

    async def load(self, thread_id: str) -> ThreadSnapshot | None:
        """Return the trusted state/history snapshot, or ``None`` for a new thread."""

        ...

    async def save(
        self,
        state: MiaState,
        messages: Sequence[ModelMessage],
    ) -> None:
        """Persist updated job state and PydanticAI history for the next turn."""

        ...


class SQLiteThreadStore:
    """Persist Agent V2 threads in the local SQLite development store.

    The runtime calls ``load`` before a turn and ``save`` afterward. Replacing
    this class with a production store does not change the agent or API contract.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=15)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_threads (
                    thread_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    messages_json BLOB NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    async def load(self, thread_id: str) -> ThreadSnapshot | None:
        """Load state and model history previously saved under ``thread_id``."""

        return self._load(thread_id)

    def _load(self, thread_id: str) -> ThreadSnapshot | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state_json, messages_json FROM agent_threads WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        if row is None:
            return None
        state = MiaState.model_validate_json(row[0])
        messages = ModelMessagesTypeAdapter.validate_json(row[1])
        return ThreadSnapshot(state=state, messages=messages)

    async def save(
        self,
        state: MiaState,
        messages: Sequence[ModelMessage],
    ) -> None:
        """Serialize state and model history into their separate SQLite columns."""

        self._save(state, list(messages))

    def _save(self, state: MiaState, messages: list[ModelMessage]) -> None:
        state_json = state.model_dump_json()
        messages_json = ModelMessagesTypeAdapter.dump_json(messages)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_threads(thread_id, state_json, messages_json, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(thread_id) DO UPDATE SET
                    state_json = excluded.state_json,
                    messages_json = excluded.messages_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (state.thread_id, state_json, messages_json),
            )


class InMemoryThreadStore:
    """Deterministic test implementation of the trusted thread boundary."""

    def __init__(self) -> None:
        self._threads: dict[str, ThreadSnapshot] = {}

    async def load(self, thread_id: str) -> ThreadSnapshot | None:
        """Return a test snapshot without accessing SQLite."""

        return self._threads.get(thread_id)

    async def save(
        self,
        state: MiaState,
        messages: Sequence[ModelMessage],
    ) -> None:
        """Copy state and messages so later test mutations cannot alter history."""

        copied_state = state.model_copy(deep=True)
        copied_messages = ModelMessagesTypeAdapter.validate_json(
            ModelMessagesTypeAdapter.dump_json(list(messages))
        )
        self._threads[state.thread_id] = ThreadSnapshot(copied_state, copied_messages)
