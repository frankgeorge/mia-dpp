"""Small framework-neutral execution trace shared by current and future workflows."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from pydantic import JsonValue

from mia_dpp.domain.workflow import WorkflowEvent, WorkflowStatus


def completed_event(
    *,
    stage: str,
    started_at: datetime,
    input_count: int,
    output_count: int,
    summary: str,
    metadata: dict[str, JsonValue] | None = None,
) -> WorkflowEvent:
    """Create an event only after a real stage has completed."""

    completed_at = datetime.now(UTC)
    identity = f"{stage}\0{started_at.isoformat()}\0{completed_at.isoformat()}"
    return WorkflowEvent(
        id=f"event-{hashlib.sha256(identity.encode()).hexdigest()[:24]}",
        stage=stage,
        status=WorkflowStatus.DONE,
        started_at=started_at,
        completed_at=completed_at,
        input_count=input_count,
        output_count=output_count,
        summary=summary,
        metadata=metadata or {},
    )
