"""Focused invariants for MIA's Pydantic domain boundary."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from mia_dpp.confidence import MatchQuality, ValueFormatQuality, assess_mapping_confidence
from mia_dpp.models import (
    ConfidenceAssessment,
    EvidenceRecord,
    EvidenceStatus,
    ProductKnowledgePackage,
    SourceLocation,
)


def evidence(identifier: str, value: str | None = "value") -> EvidenceRecord:
    return EvidenceRecord(
        id=identifier,
        predicate="product.value",
        value=value,
        source_uri="urn:test:source",
        source_content_sha256="0" * 64,
        source_location=SourceLocation(excerpt="value"),
        extraction_method="test",
        extractor_name="test",
        extractor_version="1",
        status=EvidenceStatus.OBSERVED,
        acquired_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_wire_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        SourceLocation(excerpt="value", invented=True)


def test_usable_evidence_requires_a_value() -> None:
    with pytest.raises(ValidationError, match="must contain a value"):
        evidence("missing", None)


def test_product_knowledge_rejects_duplicate_evidence_ids() -> None:
    with pytest.raises(ValidationError, match="evidence IDs must be unique"):
        ProductKnowledgePackage(
            product_id="product-1",
            product_name="Product",
            evidence=(evidence("same"), evidence("same")),
        )


def test_confidence_score_cannot_disagree_with_its_factor_arithmetic() -> None:
    valid = assess_mapping_confidence(
        source_label=MatchQuality.EXACT,
        value_format=ValueFormatQuality.VALID,
        semantic_match=MatchQuality.EXACT,
        destination_candidates=1,
    )
    with pytest.raises(ValidationError, match="must equal awarded"):
        ConfidenceAssessment(
            score=0.99,
            factors=valid.factors,
            remaining_uncertainty=valid.remaining_uncertainty,
        )
