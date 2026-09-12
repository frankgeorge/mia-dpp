"""Tests for reproducible and human-readable mapping confidence."""

import pytest
from pydantic import ValidationError

from mia_dpp.resolution.confidence import (
    MatchQuality,
    ValueFormatQuality,
    assess_mapping_confidence,
)


def test_five_factors_explain_a_near_certain_mapping() -> None:
    assessment = assess_mapping_confidence(
        source_label=MatchQuality.EXACT,
        value_format=ValueFormatQuality.VALID,
        semantic_match=MatchQuality.EXACT,
        destination_candidates=1,
        corroborating_sources=1,
    )

    assert assessment.score == 0.95
    assert [factor.code for factor in assessment.factors] == [
        "source_label",
        "value_format",
        "semantic_match",
        "destination_ambiguity",
        "independent_corroboration",
    ]
    assert sum(factor.maximum for factor in assessment.factors) == 1.0
    assert assessment.remaining_uncertainty == (
        "Only one additional source corroborates the current value.",
    )


def test_history_reduces_only_destination_ambiguity() -> None:
    without_history = assess_mapping_confidence(
        source_label=MatchQuality.STRONG,
        value_format=ValueFormatQuality.PLAUSIBLE,
        semantic_match=MatchQuality.STRONG,
        destination_candidates=3,
        corroborating_sources=0,
    )
    with_history = assess_mapping_confidence(
        source_label=MatchQuality.STRONG,
        value_format=ValueFormatQuality.PLAUSIBLE,
        semantic_match=MatchQuality.STRONG,
        destination_candidates=3,
        corroborating_sources=0,
        history_confirmations=3,
    )

    before = {factor.code: factor.awarded for factor in without_history.factors}
    after = {factor.code: factor.awarded for factor in with_history.factors}
    assert after["destination_ambiguity"] == before["destination_ambiguity"] + 0.06
    assert after["independent_corroboration"] == before["independent_corroboration"] == 0.0
    assert all(
        after[code] == before[code] for code in {"source_label", "value_format", "semantic_match"}
    )
    ambiguity = next(
        factor for factor in with_history.factors if factor.code == "destination_ambiguity"
    )
    assert "does not verify the current value" in ambiguity.explanation


def test_history_does_not_inflate_an_unambiguous_mapping() -> None:
    without_history = assess_mapping_confidence(
        source_label=MatchQuality.EXACT,
        value_format=ValueFormatQuality.VALID,
        semantic_match=MatchQuality.EXACT,
        destination_candidates=1,
        corroborating_sources=0,
    )
    with_history = assess_mapping_confidence(
        source_label=MatchQuality.EXACT,
        value_format=ValueFormatQuality.VALID,
        semantic_match=MatchQuality.EXACT,
        destination_candidates=1,
        corroborating_sources=0,
        history_confirmations=100,
    )

    assert with_history.score == without_history.score == 0.85
    assert with_history.remaining_uncertainty == (
        "The current value appears in only one source and is not corroborated.",
    )


def test_incomplete_factors_each_expose_remaining_uncertainty() -> None:
    assessment = assess_mapping_confidence(
        source_label=MatchQuality.WEAK,
        value_format=ValueFormatQuality.UNKNOWN,
        semantic_match=MatchQuality.STRONG,
        destination_candidates=2,
    )

    assert assessment.score == 0.46
    assert len(assessment.remaining_uncertainty) == 5
    assert all(assessment.remaining_uncertainty)


@pytest.mark.parametrize(
    ("field", "value"),
    (("destination_candidates", 0), ("corroborating_sources", -1)),
)
def test_counts_are_validated(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        if field == "destination_candidates":
            assess_mapping_confidence(
                source_label=MatchQuality.EXACT,
                value_format=ValueFormatQuality.VALID,
                semantic_match=MatchQuality.EXACT,
                destination_candidates=value,
            )
        else:
            assess_mapping_confidence(
                source_label=MatchQuality.EXACT,
                value_format=ValueFormatQuality.VALID,
                semantic_match=MatchQuality.EXACT,
                destination_candidates=1,
                corroborating_sources=value,
            )
