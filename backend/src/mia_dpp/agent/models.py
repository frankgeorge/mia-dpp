"""Contracts owned by the resumable MIA agent."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from mia_dpp.domain.base import WireModel
from mia_dpp.domain.mappings import GraphEntry, SemanticReviewItem
from mia_dpp.domain.workflow import AgentRunStatus
from mia_dpp.tools.mapping.models import WebsiteIngestResponse


class AgentMessageRequest(WireModel):
    thread_id: str | None = Field(default=None, min_length=8, max_length=128)
    message: str = Field(min_length=1, max_length=4096)
    graph: tuple[GraphEntry, ...] = ()


class AgentReviewDecision(WireModel):
    review_id: str = Field(pattern=r"^review-[0-9a-f]{24}$")
    decision: Literal["approve", "correct", "reject"]
    corrected_requirement_id: str | None = Field(default=None, pattern=r"^req-[0-9a-f]{24}$")
    corrected_value: str | None = Field(default=None, min_length=1, max_length=4096)
    comment: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def correction_has_a_change(self) -> AgentReviewDecision:
        changed = self.corrected_requirement_id or self.corrected_value
        if self.decision == "correct" and not changed:
            raise ValueError("a correction must change the target or value")
        if self.decision != "correct" and changed:
            raise ValueError("only a correction may include a corrected target or value")
        return self


class AgentReviewRequest(WireModel):
    thread_id: str = Field(min_length=8, max_length=128)
    decisions: tuple[AgentReviewDecision, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def review_ids_are_unique(self) -> AgentReviewRequest:
        identifiers = [item.review_id for item in self.decisions]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("review decisions must be unique")
        return self


class AgentResponse(WireModel):
    thread_id: str
    reply: str
    status: AgentRunStatus
    mode: Literal["agent", "configuration_required"] = "agent"
    website_result: WebsiteIngestResponse | None = None
    review_items: tuple[SemanticReviewItem, ...] = ()
