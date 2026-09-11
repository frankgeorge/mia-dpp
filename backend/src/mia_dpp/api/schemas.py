"""HTTP request and response contracts exposed by MIA."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from mia_dpp.domain.base import WireModel
from mia_dpp.domain.completion import CompletionSummary
from mia_dpp.domain.evidence import EvidenceRecord, ProductKnowledgePackage
from mia_dpp.domain.mappings import (
    CoverageReport,
    FieldMapping,
    GraphEntry,
    MappingProposal,
    MappingResult,
    NameplateElement,
    SemanticReviewItem,
)
from mia_dpp.domain.workflow import AgentRunStatus, WorkflowEvent
from mia_dpp.llm.conversation import ChatMessage


class ChatRequest(WireModel):
    messages: tuple[ChatMessage, ...] = ()
    graph: tuple[GraphEntry, ...] = ()


class ChatResponse(WireModel):
    reply: str
    proposal: MappingProposal | None = None
    generate: bool = False
    mode: str
    nameplate_elements: tuple[NameplateElement, ...]


class WebsiteIngestRequest(WireModel):
    url: str = Field(min_length=10, max_length=2048, pattern=r"^https?://")
    graph: tuple[GraphEntry, ...] = ()
    template_keys: tuple[str, ...] = ("digital_nameplate", "technical_data")

    @model_validator(mode="after")
    def selected_template_keys_are_unique(self) -> WebsiteIngestRequest:
        if not self.template_keys:
            raise ValueError("at least one template key must be selected")
        if len(self.template_keys) != len(set(self.template_keys)):
            raise ValueError("selected template keys must be unique")
        return self


class WebsiteIngestResponse(WireModel):
    reply: str
    source_url: str
    proposal: MappingProposal
    evidence: tuple[EvidenceRecord, ...]
    knowledge_package: ProductKnowledgePackage
    mapping_result: MappingResult
    coverage_report: CoverageReport
    completion_summary: CompletionSummary
    workflow_events: tuple[WorkflowEvent, ...]
    mode: Literal["website"] = "website"
    nameplate_elements: tuple[NameplateElement, ...]

    @model_validator(mode="after")
    def legacy_evidence_matches_knowledge_package(self) -> WebsiteIngestResponse:
        if self.evidence != self.knowledge_package.evidence:
            raise ValueError("evidence must match knowledgePackage.evidence")
        proposal = (*self.mapping_result.mapped, *self.mapping_result.ambiguous)
        if self.proposal.mappings != proposal:
            raise ValueError("proposal mappings must match mappingResult")
        if self.coverage_report.analyzed_evidence_ids != tuple(item.id for item in self.evidence):
            raise ValueError("coverageReport must analyze every evidence record in order")
        return self


class AgentMessageRequest(WireModel):
    thread_id: str | None = Field(default=None, min_length=8, max_length=128)
    message: str = Field(min_length=1, max_length=4096)
    graph: tuple[GraphEntry, ...] = ()


class AgentReviewDecision(WireModel):
    review_id: str = Field(pattern=r"^review-[0-9a-f]{24}$")
    decision: Literal["approve", "correct", "reject"]
    corrected_requirement_id: str | None = Field(
        default=None,
        pattern=r"^req-[0-9a-f]{24}$",
    )
    corrected_value: str | None = Field(default=None, min_length=1, max_length=4096)
    comment: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def correction_has_a_change(self) -> AgentReviewDecision:
        if self.decision == "correct" and not (
            self.corrected_requirement_id or self.corrected_value
        ):
            raise ValueError("a correction must change the target or value")
        if self.decision != "correct" and (
            self.corrected_requirement_id is not None or self.corrected_value is not None
        ):
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
    """One resumable MIA graph result returned to the workspace."""

    thread_id: str
    reply: str
    status: AgentRunStatus
    mode: Literal["agent", "configuration_required"] = "agent"
    website_result: WebsiteIngestResponse | None = None
    review_items: tuple[SemanticReviewItem, ...] = ()


class DppBuildRequest(WireModel):
    product_name: str
    mappings: tuple[FieldMapping, ...]
    evidence: tuple[EvidenceRecord, ...] = ()


class HealthResponse(WireModel):
    status: Literal["ok", "not_ready"]
    version: str
    standards_ready: bool
    standards_commit: str
