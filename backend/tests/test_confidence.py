"""Tests for the small deterministic mapping assessment policy."""

import pytest

from mia_dpp.domain.mappings import MappingBasis
from mia_dpp.tools.mapping.confidence import MatchQuality, ValueFormatQuality, assess_mapping


def test_exact_unambiguous_mapping_does_not_require_review() -> None:
    assessment = assess_mapping(
        source_label=MatchQuality.EXACT,
        value_format=ValueFormatQuality.VALID,
        semantic_match=MatchQuality.EXACT,
        destination_candidates=1,
    )

    assert assessment.basis is MappingBasis.EXACT
    assert not assessment.review_required
    assert assessment.uncertainties == ()


def test_destination_ambiguity_requires_review() -> None:
    assessment = assess_mapping(
        source_label=MatchQuality.STRONG,
        value_format=ValueFormatQuality.PLAUSIBLE,
        semantic_match=MatchQuality.STRONG,
        destination_candidates=3,
    )

    assert assessment.basis is MappingBasis.EXACT
    assert assessment.review_required
    assert assessment.uncertainties == ("3 compatible target destinations remain.",)


def test_weak_or_unvalidated_signals_require_review() -> None:
    assessment = assess_mapping(
        source_label=MatchQuality.WEAK,
        value_format=ValueFormatQuality.UNKNOWN,
        semantic_match=MatchQuality.WEAK,
        destination_candidates=1,
    )

    assert assessment.review_required
    assert len(assessment.uncertainties) == 3


def test_destination_count_is_validated() -> None:
    with pytest.raises(ValueError, match="at least one"):
        assess_mapping(
            source_label=MatchQuality.EXACT,
            value_format=ValueFormatQuality.VALID,
            semantic_match=MatchQuality.EXACT,
            destination_candidates=0,
        )
