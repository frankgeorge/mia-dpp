"""Durable reviewed mapping knowledge used as bounded semantic reference context."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from mia_dpp.domain.mappings import ProposedFieldMapping
from mia_dpp.tools.mapping.models import MappingKnowledgeEntry, MappingKnowledgeStatus


class MappingKnowledgeStore:
    """Persist candidate proposals and promote only human-reviewed mappings to trusted."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS mapping_knowledge "
            "(id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )
        self._connection.commit()

    def remember_candidate(
        self,
        mapping: ProposedFieldMapping,
        *,
        manufacturer: str | None,
        domain: str | None,
        product_family: str | None,
    ) -> MappingKnowledgeEntry:
        return self._upsert(
            mapping,
            manufacturer=manufacturer,
            domain=domain,
            product_family=product_family,
            status=MappingKnowledgeStatus.CANDIDATE,
        )

    def remember_review(
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
        return self._upsert(
            mapping,
            manufacturer=manufacturer,
            domain=domain,
            product_family=product_family,
            status=status,
            decision=decision,
            comment=comment,
        )

    def list(self) -> tuple[MappingKnowledgeEntry, ...]:
        rows = self._connection.execute(
            "SELECT payload FROM mapping_knowledge ORDER BY rowid DESC"
        ).fetchall()
        return tuple(MappingKnowledgeEntry.model_validate_json(row[0]) for row in rows)

    def relevant(
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
            for item in self.list()
            if item.status is MappingKnowledgeStatus.TRUSTED
            and item.target_template in template_keys
            and self._normalize(item.source_field) == label
            and (not item.domain or not domain or item.domain == domain)
            and (not item.manufacturer or not manufacturer or item.manufacturer == manufacturer)
        )

    def _upsert(
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
        row = self._connection.execute(
            "SELECT payload FROM mapping_knowledge WHERE id = ?", (entry_id,)
        ).fetchone()
        existing = MappingKnowledgeEntry.model_validate_json(row[0]) if row else None
        now = datetime.now(UTC)
        values = tuple(
            dict.fromkeys((*((existing.example_values) if existing else ()), mapping.source_value))
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
        self._connection.execute(
            "INSERT OR REPLACE INTO mapping_knowledge(id, payload) VALUES (?, ?)",
            (entry.id, entry.model_dump_json()),
        )
        self._connection.commit()
        return entry

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.casefold().split())
