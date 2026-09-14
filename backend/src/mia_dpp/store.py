"""Trusted session and deferred-call persistence for MIA."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any

from pydantic import AwareDatetime
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from mia_dpp.agent.models import HumanRequest, HumanRequestKind, MiaState
from mia_dpp.domain.base import WireModel
from mia_dpp.domain.mappings import ProposedFieldMapping
from mia_dpp.tools.mapping.models import MappingKnowledgeEntry, MappingKnowledgeStatus

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")


class ArtifactKind(StrEnum):
    SEARCH = "search"
    SOURCE = "source"
    RAW = "raw"
    EVIDENCE = "evidence"
    MAPPING = "mapping"
    COVERAGE = "coverage"
    REVIEW = "review"
    AAS = "aas"
    VALIDATION = "validation"
    TRACE = "trace"
    EXPORT = "export"


class WorkspaceArtifact(WireModel):
    """Inspectable artifact metadata; contents remain in the artifact directory."""

    id: str
    kind: ArtifactKind
    name: str
    relative_path: str
    created_at: AwareDatetime
    created_by: str
    content_type: str
    sha256: str
    size: int
    product_id: str | None = None
    source_url: str | None = None
    derived_from: tuple[str, ...] = ()
    downloadable: bool = True


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


@dataclass(frozen=True)
class ResolvedCall(PendingCall):
    """A trusted result persisted before the model continuation starts."""

    result: dict[str, Any]


class Store:
    """Persist sessions and enforce one-time consumption of deferred calls.

    MIA owns this small SQLite store rather than relying on graph checkpoints.
    Database creation is lazy, so importing the ASGI application does not lock
    a shared development database.
    """

    def __init__(self, path: Path, artifact_root: Path | None = None) -> None:
        self._path = path
        self._artifact_root = (artifact_root or path.with_suffix(".artifacts")).resolve()
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

    def save(
        self,
        snapshot: SessionSnapshot,
        *,
        deferred_calls: list[tuple[str, HumanRequest]] | None = None,
        completed_call_ids: tuple[str, ...] = (),
    ) -> None:
        """Atomically save a turn and its deferred-call state transitions."""

        session_id = snapshot.state.thread_id
        self._validate_id(session_id, "session")
        with self._connect() as connection:
            self._save_session(connection, snapshot)
            self._insert_deferred(connection, session_id, deferred_calls or [])
            for call_id in completed_call_ids:
                changed = connection.execute(
                    "UPDATE deferred_calls SET status='completed' "
                    "WHERE call_id=? AND session_id=? AND status='resolved'",
                    (call_id, session_id),
                ).rowcount
                if changed != 1:
                    raise ValueError("resolved deferred call could not be completed")

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

    def resolve(
        self,
        snapshot: SessionSnapshot,
        call_id: str,
        *,
        expected_kind: HumanRequestKind,
        result: dict[str, Any],
    ) -> ResolvedCall:
        """Persist a trusted result and updated state before model continuation."""

        session_id = snapshot.state.thread_id
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
                "UPDATE deferred_calls SET status='resolved', resolved_at=?, result_sha256=?, "
                "result_json=? "
                "WHERE call_id=? AND session_id=? AND status='pending'",
                (
                    datetime.now(UTC).isoformat(),
                    hashlib.sha256(payload.encode()).hexdigest(),
                    payload,
                    call_id,
                    session_id,
                ),
            ).rowcount
            if changed != 1:
                raise ValueError("deferred call was consumed concurrently")
            self._save_session(connection, snapshot)
        return ResolvedCall(
            call_id=call_id,
            session_id=session_id,
            request=request,
            result=result,
        )

    def resolved(self, session_id: str) -> tuple[ResolvedCall, ...]:
        """Return trusted results whose model continuation has not completed."""

        self._validate_id(session_id, "session")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT call_id, request_json, result_json FROM deferred_calls "
                "WHERE session_id=? AND status='resolved' ORDER BY resolved_at, call_id",
                (session_id,),
            ).fetchall()
        return tuple(
            ResolvedCall(
                call_id=row[0],
                session_id=session_id,
                request=HumanRequest.model_validate_json(row[1]),
                result=json.loads(row[2]),
            )
            for row in rows
        )

    def write_json(
        self,
        thread_id: str,
        kind: ArtifactKind,
        name: str,
        value: Any,
        **metadata: Any,
    ) -> WorkspaceArtifact:
        data = json.dumps(value, ensure_ascii=False, indent=2, default=str).encode()
        return self.write_bytes(
            thread_id, kind, name, data, content_type="application/json", **metadata
        )

    def write_bytes(
        self,
        thread_id: str,
        kind: ArtifactKind,
        name: str,
        data: bytes,
        *,
        content_type: str,
        **metadata: Any,
    ) -> WorkspaceArtifact:
        """Write one artifact file and register its metadata in SQLite."""

        directory = self._thread_dir(thread_id)
        category = directory / kind.value
        category.mkdir(parents=True, exist_ok=True)
        artifact_id = "artifact-" + uuid.uuid4().hex
        relative = f"{kind.value}/{artifact_id}-{self._safe_name(name)}"
        (directory / relative).write_bytes(data)
        artifact = WorkspaceArtifact(
            id=artifact_id,
            kind=kind,
            name=name,
            relative_path=relative,
            created_at=datetime.now(UTC),
            created_by=str(metadata.get("created_by", "mia")),
            product_id=metadata.get("product_id"),
            source_url=metadata.get("source_url"),
            derived_from=tuple(metadata.get("derived_from", ())),
            content_type=content_type,
            sha256=hashlib.sha256(data).hexdigest(),
            size=len(data),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO artifacts(id, session_id, payload) VALUES (?, ?, ?)",
                (artifact.id, thread_id, artifact.model_dump_json()),
            )
        return artifact

    def list_artifacts(self, thread_id: str) -> tuple[WorkspaceArtifact, ...]:
        self._validate_id(thread_id, "session")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM artifacts WHERE session_id=? ORDER BY rowid", (thread_id,)
            ).fetchall()
        return tuple(WorkspaceArtifact.model_validate_json(row[0]) for row in rows)

    def read_artifact(self, thread_id: str, artifact_id: str) -> tuple[WorkspaceArtifact, bytes]:
        self._validate_id(thread_id, "session")
        self._validate_id(artifact_id, "artifact")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM artifacts WHERE id=? AND session_id=?",
                (artifact_id, thread_id),
            ).fetchone()
        if row is None:
            raise KeyError("unknown artifact")
        artifact = WorkspaceArtifact.model_validate_json(row[0])
        directory = self._thread_dir(thread_id)
        path = (directory / artifact.relative_path).resolve()
        if directory not in path.parents:
            raise ValueError("artifact path escapes workspace")
        return artifact, path.read_bytes()

    def export_zip(self, thread_id: str) -> bytes:
        artifacts = self.list_artifacts(thread_id)
        output = BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "manifest.json",
                json.dumps([item.model_dump(mode="json") for item in artifacts], indent=2),
            )
            archive.writestr(
                "exports/workspace.json",
                json.dumps(self.combined_export(thread_id), indent=2),
            )
            for artifact in artifacts:
                _, data = self.read_artifact(thread_id, artifact.id)
                archive.writestr(artifact.relative_path, data)
        return output.getvalue()

    def combined_export(self, thread_id: str) -> dict[str, Any]:
        artifacts = self.list_artifacts(thread_id)
        contents: dict[str, Any] = {}
        for artifact in artifacts:
            if artifact.content_type == "application/json":
                _, data = self.read_artifact(thread_id, artifact.id)
                contents[artifact.id] = json.loads(data)
        return {
            "artifacts": [item.model_dump(mode="json") for item in artifacts],
            "jsonArtifacts": contents,
        }

    def remember_mapping_candidate(
        self,
        mapping: ProposedFieldMapping,
        *,
        manufacturer: str | None,
        domain: str | None,
        product_family: str | None,
    ) -> MappingKnowledgeEntry:
        return self._upsert_mapping_knowledge(
            mapping,
            manufacturer=manufacturer,
            domain=domain,
            product_family=product_family,
            status=MappingKnowledgeStatus.CANDIDATE,
        )

    def remember_mapping_review(
        self,
        mapping: ProposedFieldMapping,
        *,
        decision: str,
        manufacturer: str | None,
        domain: str | None,
        product_family: str | None,
        comment: str | None,
    ) -> MappingKnowledgeEntry:
        status = (
            MappingKnowledgeStatus.TRUSTED
            if decision in {"approve", "correct"}
            else MappingKnowledgeStatus.CANDIDATE
        )
        return self._upsert_mapping_knowledge(
            mapping,
            manufacturer=manufacturer,
            domain=domain,
            product_family=product_family,
            status=status,
            decision=decision,
            comment=comment,
        )

    def list_mapping_knowledge(self) -> tuple[MappingKnowledgeEntry, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM mapping_knowledge ORDER BY rowid DESC"
            ).fetchall()
        return tuple(MappingKnowledgeEntry.model_validate_json(row[0]) for row in rows)

    def relevant_mapping_knowledge(
        self,
        source_field: str,
        *,
        manufacturer: str | None,
        domain: str | None,
        template_keys: tuple[str, ...],
    ) -> tuple[MappingKnowledgeEntry, ...]:
        label = self._normalize(source_field)
        return tuple(
            item
            for item in self.list_mapping_knowledge()
            if item.status is MappingKnowledgeStatus.TRUSTED
            and item.target_template in template_keys
            and self._normalize(item.source_field) == label
            and (not item.domain or not domain or item.domain == domain)
            and (not item.manufacturer or not manufacturer or item.manufacturer == manufacturer)
        )

    def _upsert_mapping_knowledge(
        self,
        mapping: ProposedFieldMapping,
        *,
        manufacturer: str | None,
        domain: str | None,
        product_family: str | None,
        status: MappingKnowledgeStatus,
        decision: str | None = None,
        comment: str | None = None,
    ) -> MappingKnowledgeEntry:
        identity = "\0".join(
            (
                self._normalize(mapping.source_field),
                domain or "",
                mapping.target.template_key,
                "/".join(mapping.target.template_path),
            )
        )
        entry_id = "knowledge-" + hashlib.sha256(identity.encode()).hexdigest()[:24]
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM mapping_knowledge WHERE id=?", (entry_id,)
            ).fetchone()
            existing = MappingKnowledgeEntry.model_validate_json(row[0]) if row else None
            now = datetime.now(UTC)
            values = tuple(
                dict.fromkeys(
                    (*((existing.example_values) if existing else ()), mapping.source_value)
                )
            )
            comments = tuple(
                dict.fromkeys(
                    (
                        *((existing.human_comments) if existing else ()),
                        *((comment,) if comment else ()),
                    )
                )
            )
            entry = MappingKnowledgeEntry(
                id=entry_id,
                source_field=mapping.source_field,
                example_values=values[-5:],
                target_template=mapping.target.template_key,
                target_path=mapping.target.template_path,
                semantic_id=mapping.semantic_id,
                manufacturer=manufacturer,
                domain=domain,
                product_family=product_family,
                llm_review_summary=(mapping.llm_review.conclusion if mapping.llm_review else None),
                human_comments=comments,
                confirmations=(existing.confirmations if existing else 0) + (decision == "approve"),
                corrections=(existing.corrections if existing else 0) + (decision == "correct"),
                rejections=(existing.rejections if existing else 0) + (decision == "reject"),
                created_at=existing.created_at if existing else now,
                updated_at=now,
                status=(
                    status
                    if status is MappingKnowledgeStatus.TRUSTED
                    else (existing.status if existing else status)
                ),
            )
            connection.execute(
                "INSERT OR REPLACE INTO mapping_knowledge(id, payload) VALUES (?, ?)",
                (entry.id, entry.model_dump_json()),
            )
        return entry

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
                    "resolved_at TEXT, result_sha256 TEXT, result_json TEXT, "
                    "FOREIGN KEY(session_id) REFERENCES sessions(id))"
                )
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(deferred_calls)")
                }
                if "result_json" not in columns:
                    connection.execute("ALTER TABLE deferred_calls ADD COLUMN result_json TEXT")
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS deferred_calls_session_status "
                    "ON deferred_calls(session_id, status)"
                )
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS artifacts ("
                    "id TEXT PRIMARY KEY, session_id TEXT NOT NULL, payload TEXT NOT NULL)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS artifacts_session ON artifacts(session_id)"
                )
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS mapping_knowledge ("
                    "id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
                )
            self._ready = True

    @staticmethod
    def _save_session(connection: sqlite3.Connection, snapshot: SessionSnapshot) -> None:
        history = ModelMessagesTypeAdapter.dump_json(snapshot.history).decode()
        connection.execute(
            "INSERT INTO sessions"
            "(id, state_json, history_json, reply, decision_summary, trace_offset, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "state_json=excluded.state_json, history_json=excluded.history_json, "
            "reply=excluded.reply, decision_summary=excluded.decision_summary, "
            "trace_offset=excluded.trace_offset, updated_at=excluded.updated_at",
            (
                snapshot.state.thread_id,
                snapshot.state.model_dump_json(exclude_computed_fields=True),
                history,
                snapshot.reply,
                snapshot.decision_summary,
                snapshot.trace_offset,
                datetime.now(UTC).isoformat(),
            ),
        )

    @classmethod
    def _insert_deferred(
        cls,
        connection: sqlite3.Connection,
        session_id: str,
        calls: list[tuple[str, HumanRequest]],
    ) -> None:
        for call_id, request in calls:
            cls._validate_call_id(call_id)
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

    @staticmethod
    def _validate_id(value: str, label: str) -> None:
        if not _SAFE_ID.fullmatch(value):
            raise ValueError(f"invalid {label} ID")

    @staticmethod
    def _validate_call_id(value: str) -> None:
        if not value or len(value) > 512 or "\x00" in value:
            raise ValueError("invalid deferred call ID")

    def _thread_dir(self, thread_id: str) -> Path:
        self._validate_id(thread_id, "session")
        path = (self._artifact_root / thread_id).resolve()
        if self._artifact_root not in path.parents:
            raise ValueError("thread path escapes artifact root")
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _safe_name(name: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(name).name).strip("-.")
        return cleaned or "artifact"

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.casefold().split())
