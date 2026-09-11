"""Framework-neutral workflow status and trace records."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, Field, JsonValue, model_validator

from mia_dpp.domain.base import WireModel


class WorkflowStatus(StrEnum):
    DONE = "done"
    FAILED = "failed"


class AgentRunStatus(StrEnum):
    COMPLETED = "completed"
    AWAITING_REVIEW = "awaiting_review"
    AWAITING_INPUT = "awaiting_input"
    AWAITING_OPTIONAL_CHOICE = "awaiting_optional_choice"


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
