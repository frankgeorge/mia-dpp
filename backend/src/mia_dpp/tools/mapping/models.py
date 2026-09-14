"""Application contracts for product website resolution."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from mia_dpp.domain.base import WireModel
from mia_dpp.domain.evidence import EvidenceRecord
from mia_dpp.domain.targets import Requirement


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
