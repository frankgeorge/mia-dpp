"""Trusted session and deferred-call persistence for MIA."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from mia_dpp.agent.models import HumanRequest, HumanRequestKind, MiaState

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")


@dataclass(frozen=True)
class SessionSnapshot:
    """Trusted workflow state and model history loaded for one conversation."""

    state: MiaState
    history: list[ModelMessage]
    reply: str = ""
    decision_summary: str = ""
    trace_offset: int = 0


@dataclass(frozen=True)
class PendingCall:
    """One unconsumed external result expected from a trusted human action."""

    call_id: str
    session_id: str
    request: HumanRequest


class Store:
    """Persist sessions and enforce one-time consumption of deferred calls.

    MIA owns this small SQLite store rather than relying on graph checkpoints.
    Database creation is lazy, so importing the ASGI application does not lock
    a shared development database.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._setup_lock = Lock()
        self._ready = False

    def load(self, session_id: str) -> SessionSnapshot | None:
        self._validate_id(session_id, "session")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state_json, history_json, reply, decision_summary, trace_offset "
                "FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return SessionSnapshot(
            state=MiaState.model_validate_json(row[0]),
            history=list(ModelMessagesTypeAdapter.validate_json(row[1])),
            reply=row[2],
            decision_summary=row[3],
            trace_offset=int(row[4]),
        )

    def save(self, snapshot: SessionSnapshot) -> None:
        session_id = snapshot.state.thread_id
        self._validate_id(session_id, "session")
        history = ModelMessagesTypeAdapter.dump_json(snapshot.history).decode()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO sessions"
                "(id, state_json, history_json, reply, decision_summary, trace_offset, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "state_json=excluded.state_json, history_json=excluded.history_json, "
                "reply=excluded.reply, decision_summary=excluded.decision_summary, "
                "trace_offset=excluded.trace_offset, updated_at=excluded.updated_at",
                (
                    session_id,
                    snapshot.state.model_dump_json(),
                    history,
                    snapshot.reply,
                    snapshot.decision_summary,
                    snapshot.trace_offset,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def remember_deferred(
        self,
        session_id: str,
        calls: list[tuple[str, HumanRequest]],
    ) -> None:
        self._validate_id(session_id, "session")
        with self._connect() as connection:
            for call_id, request in calls:
                self._validate_call_id(call_id)
                connection.execute(
                    "INSERT INTO deferred_calls"
                    "(call_id, session_id, kind, request_json, status, created_at) "
                    "VALUES (?, ?, ?, ?, 'pending', ?)",
                    (
                        call_id,
                        session_id,
                        request.kind.value,
                        request.model_dump_json(),
                        datetime.now(UTC).isoformat(),
                    ),
                )

    def pending(self, session_id: str) -> tuple[PendingCall, ...]:
        self._validate_id(session_id, "session")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT call_id, request_json FROM deferred_calls "
                "WHERE session_id = ? AND status = 'pending' ORDER BY created_at, call_id",
                (session_id,),
            ).fetchall()
        return tuple(
            PendingCall(
                call_id=row[0],
                session_id=session_id,
                request=HumanRequest.model_validate_json(row[1]),
            )
            for row in rows
        )

    def consume(
        self,
        session_id: str,
        call_id: str,
        *,
        expected_kind: HumanRequestKind,
        result: dict[str, Any],
    ) -> PendingCall:
        """Atomically consume one expected call, rejecting wrong IDs and replays."""

        self._validate_id(session_id, "session")
        self._validate_call_id(call_id)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT request_json, status FROM deferred_calls "
                "WHERE call_id = ? AND session_id = ?",
                (call_id, session_id),
            ).fetchone()
            if row is None:
                raise ValueError("unknown deferred call for this session")
            if row[1] != "pending":
                raise ValueError("deferred call has already been consumed")
            request = HumanRequest.model_validate_json(row[0])
            if request.kind is not expected_kind:
                raise ValueError("deferred call does not accept this human action")
            payload = json.dumps(result, sort_keys=True, separators=(",", ":"))
            changed = connection.execute(
                "UPDATE deferred_calls SET status='consumed', resolved_at=?, result_sha256=? "
                "WHERE call_id=? AND session_id=? AND status='pending'",
                (
                    datetime.now(UTC).isoformat(),
                    hashlib.sha256(payload.encode()).hexdigest(),
                    call_id,
                    session_id,
                ),
            ).rowcount
            if changed != 1:
                raise ValueError("deferred call was consumed concurrently")
        return PendingCall(call_id=call_id, session_id=session_id, request=request)

    def _connect(self) -> sqlite3.Connection:
        self._setup()
        connection = sqlite3.connect(self._path, timeout=10)
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _setup(self) -> None:
        if self._ready:
            return
        with self._setup_lock:
            if self._ready:
                return
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self._path, timeout=10) as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("PRAGMA busy_timeout = 10000")
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS sessions ("
                    "id TEXT PRIMARY KEY, state_json TEXT NOT NULL, history_json TEXT NOT NULL, "
                    "reply TEXT NOT NULL, decision_summary TEXT NOT NULL, "
                    "trace_offset INTEGER NOT NULL, updated_at TEXT NOT NULL)"
                )
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS deferred_calls ("
                    "call_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, kind TEXT NOT NULL, "
                    "request_json TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, "
                    "resolved_at TEXT, result_sha256 TEXT, "
                    "FOREIGN KEY(session_id) REFERENCES sessions(id))"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS deferred_calls_session_status "
                    "ON deferred_calls(session_id, status)"
                )
            self._ready = True

    @staticmethod
    def _validate_id(value: str, label: str) -> None:
        if not _SAFE_ID.fullmatch(value):
            raise ValueError(f"invalid {label} ID")

    @staticmethod
    def _validate_call_id(value: str) -> None:
        if not value or len(value) > 512 or "\x00" in value:
            raise ValueError("invalid deferred call ID")
