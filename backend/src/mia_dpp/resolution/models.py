"""Application contracts for product website resolution."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from mia_dpp.domain.base import WireModel
from mia_dpp.domain.completion import CompletionSummary
from mia_dpp.domain.evidence import EvidenceRecord, ProductKnowledgePackage
from mia_dpp.domain.mappings import (
    CoverageReport,
    GraphEntry,
    MappingProposal,
    MappingResult,
    NameplateElement,
)
from mia_dpp.domain.workflow import WorkflowEvent


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
