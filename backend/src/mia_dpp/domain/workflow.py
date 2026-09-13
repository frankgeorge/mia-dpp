"""Framework-neutral workflow status and trace records."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import AwareDatetime, Field, JsonValue, model_validator

from mia_dpp.domain.base import WireModel


class WorkflowStatus(StrEnum):
    DONE = "done"
    FAILED = "failed"


class WorkflowEvent(WireModel):
    """Framework-neutral record of one execution stage that actually ran."""

    id: str = Field(min_length=1)
    stage: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    status: WorkflowStatus
    started_at: AwareDatetime
    completed_at: AwareDatetime
    input_count: int = Field(ge=0)
    output_count: int = Field(ge=0)
    summary: str = Field(min_length=1)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def completion_follows_start(self) -> WorkflowEvent:
        if self.completed_at < self.started_at:
            raise ValueError("workflow event completedAt cannot precede startedAt")
        return self


def completed_event(
    *,
    stage: str,
    started_at: datetime,
    input_count: int,
    output_count: int,
    summary: str,
    metadata: dict[str, JsonValue] | None = None,
) -> WorkflowEvent:
    """Create a trace event only after a real stage has completed."""

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
