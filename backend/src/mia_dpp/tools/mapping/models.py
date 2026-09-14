"""Application contracts for product website resolution."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import computed_field

from mia_dpp.domain.base import WireModel
from mia_dpp.domain.completion import CompletionSummary, build_completion_summary
from mia_dpp.domain.evidence import EvidenceRecord, ProductKnowledgePackage
from mia_dpp.domain.mappings import (
    CoverageReport,
    MappingProposal,
    MappingResult,
    NameplateElement,
)
from mia_dpp.domain.targets import Requirement, TemplateIndex
from mia_dpp.tools.mapping.coverage import coverage


class WebsiteIngestResponse(WireModel):
    reply: str
    source_url: str
    knowledge_package: ProductKnowledgePackage
    mapping_result: MappingResult
    template_index: TemplateIndex
    mode: Literal["website"] = "website"
    nameplate_elements: tuple[NameplateElement, ...]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def evidence(self) -> tuple[EvidenceRecord, ...]:
        """Compatibility view derived from the authoritative knowledge package."""

        return self.knowledge_package.evidence

    @computed_field  # type: ignore[prop-decorator]
    @property
    def proposal(self) -> MappingProposal:
        """Compatibility view derived from the authoritative mapping result."""

        return MappingProposal(
            product_name=self.knowledge_package.product_name,
            mappings=(
                *self.mapping_result.mapped,
                *self.mapping_result.ambiguous,
                *self.mapping_result.rejected,
            ),
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def coverage_report(self) -> CoverageReport:
        """Derive coverage from official targets and current mappings."""

        return coverage(
            self.knowledge_package,
            self.template_index,
            mapping_result=self.mapping_result,
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def completion_summary(self) -> CompletionSummary:
        """Derive the human completion view from current authoritative data."""

        return build_completion_summary(
            self.coverage_report,
            self.mapping_result,
            self.knowledge_package.evidence,
        )


class SemanticMappingContext(WireModel):
    """Bounded unresolved data safe to provide to semantic reasoning."""

    product_id: str
    evidence: tuple[EvidenceRecord, ...]
    requirements: tuple[Requirement, ...]


class MappingKnowledgeStatus(StrEnum):
    CANDIDATE = "candidate"
    TRUSTED = "trusted"


class MappingKnowledgeEntry(WireModel):
    """Reviewed mapping knowledge reusable as non-authoritative semantic context."""

    id: str
    source_field: str
    example_values: tuple[str, ...]
    target_template: str
    target_path: tuple[str, ...]
    semantic_id: str
    manufacturer: str | None = None
    domain: str | None = None
    product_family: str | None = None
    llm_review_summary: str | None = None
    human_comments: tuple[str, ...] = ()
    confirmations: int = 0
    corrections: int = 0
    rejections: int = 0
    created_at: datetime
    updated_at: datetime
    status: MappingKnowledgeStatus
