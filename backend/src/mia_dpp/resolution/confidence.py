"""Deterministic and explainable confidence scoring for mapping proposals.

The score measures how well the available evidence supports a mapping.  It is
not a probability and it never treats an earlier mapping as proof that the
current product value is correct.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field, validate_call

from mia_dpp.domain.mappings import ConfidenceAssessment, ConfidenceFactor


class MatchQuality(StrEnum):
    """Deterministic strength assigned by an extractor or mapping rule."""

    NONE = "none"
    WEAK = "weak"
    STRONG = "strong"
    EXACT = "exact"


class ValueFormatQuality(StrEnum):
    """Result of checking a value against the target's expected format."""

    INVALID = "invalid"
    UNKNOWN = "unknown"
    PLAUSIBLE = "plausible"
    VALID = "valid"


_SOURCE_LABEL_POINTS = {
    MatchQuality.NONE: 0.0,
    MatchQuality.WEAK: 0.08,
    MatchQuality.STRONG: 0.16,
    MatchQuality.EXACT: 0.20,
}
_SOURCE_LABEL_EXPLANATIONS = {
    MatchQuality.NONE: "The source provides no label that identifies this field.",
    MatchQuality.WEAK: "The source label is only an approximate match.",
    MatchQuality.STRONG: "The source label is a recognized synonym for the target.",
    MatchQuality.EXACT: "The source label explicitly names the target field.",
}
_SOURCE_LABEL_UNCERTAINTIES = {
    MatchQuality.NONE: "No useful source label supports the mapping.",
    MatchQuality.WEAK: "The source label could describe a different field.",
    MatchQuality.STRONG: "The label is a synonym rather than the exact target name.",
    MatchQuality.EXACT: None,
}

_VALUE_FORMAT_POINTS = {
    ValueFormatQuality.INVALID: 0.0,
    ValueFormatQuality.UNKNOWN: 0.04,
    ValueFormatQuality.PLAUSIBLE: 0.10,
    ValueFormatQuality.VALID: 0.15,
}
_VALUE_FORMAT_EXPLANATIONS = {
    ValueFormatQuality.INVALID: "The value fails the target's format check.",
    ValueFormatQuality.UNKNOWN: "No deterministic format rule is available for this value.",
    ValueFormatQuality.PLAUSIBLE: "The value is plausible but not fully validated.",
    ValueFormatQuality.VALID: "The value satisfies the target's deterministic format check.",
}
_VALUE_FORMAT_UNCERTAINTIES = {
    ValueFormatQuality.INVALID: "The value is incompatible with the expected target format.",
    ValueFormatQuality.UNKNOWN: "The value format has not been validated.",
    ValueFormatQuality.PLAUSIBLE: "The value passes only a partial format check.",
    ValueFormatQuality.VALID: None,
}

_SEMANTIC_MATCH_POINTS = {
    MatchQuality.NONE: 0.0,
    MatchQuality.WEAK: 0.10,
    MatchQuality.STRONG: 0.20,
    MatchQuality.EXACT: 0.25,
}
_SEMANTIC_MATCH_EXPLANATIONS = {
    MatchQuality.NONE: "No semantic relationship to the target was established.",
    MatchQuality.WEAK: "The source and target have only a broad semantic relationship.",
    MatchQuality.STRONG: "The source meaning closely matches the target definition.",
    MatchQuality.EXACT: "The source meaning exactly matches the target definition.",
}
_SEMANTIC_MATCH_UNCERTAINTIES = {
    MatchQuality.NONE: "The semantic meaning of the mapping is unsupported.",
    MatchQuality.WEAK: "The semantic relationship is broad and may be misleading.",
    MatchQuality.STRONG: "A small semantic distinction may remain.",
    MatchQuality.EXACT: None,
}


def _factor(
    *,
    code: str,
    label: str,
    awarded: float,
    maximum: float,
    explanation: str,
    uncertainty: str | None,
) -> ConfidenceFactor:
    return ConfidenceFactor(
        code=code,
        label=label,
        awarded=awarded,
        maximum=maximum,
        explanation=explanation,
        uncertainty=uncertainty,
    )


@validate_call
def assess_mapping_confidence(
    *,
    source_label: MatchQuality,
    value_format: ValueFormatQuality,
    semantic_match: MatchQuality,
    destination_candidates: Annotated[int, Field(ge=1)],
    corroborating_sources: Annotated[int, Field(ge=0)] = 0,
    history_confirmations: Annotated[int, Field(ge=0)] = 0,
) -> ConfidenceAssessment:
    """Assess a proposed mapping from explicit, reproducible signals.

    ``corroborating_sources`` counts *additional independent sources* that
    agree with the current value. ``history_confirmations`` counts prior human
    approvals of the same source-to-target relationship. History can reduce
    destination ambiguity, but it never corroborates the current value.
    """

    source_factor = _factor(
        code="source_label",
        label="Source label",
        awarded=_SOURCE_LABEL_POINTS[source_label],
        maximum=0.20,
        explanation=_SOURCE_LABEL_EXPLANATIONS[source_label],
        uncertainty=_SOURCE_LABEL_UNCERTAINTIES[source_label],
    )
    format_factor = _factor(
        code="value_format",
        label="Value format",
        awarded=_VALUE_FORMAT_POINTS[value_format],
        maximum=0.15,
        explanation=_VALUE_FORMAT_EXPLANATIONS[value_format],
        uncertainty=_VALUE_FORMAT_UNCERTAINTIES[value_format],
    )
    semantic_factor = _factor(
        code="semantic_match",
        label="Semantic match",
        awarded=_SEMANTIC_MATCH_POINTS[semantic_match],
        maximum=0.25,
        explanation=_SEMANTIC_MATCH_EXPLANATIONS[semantic_match],
        uncertainty=_SEMANTIC_MATCH_UNCERTAINTIES[semantic_match],
    )

    if destination_candidates == 1:
        ambiguity_points = 0.25
        ambiguity_explanation = "Only one compatible destination remains."
        if history_confirmations:
            ambiguity_explanation += (
                " Prior approvals were not needed to resolve this target and do not "
                "verify the current value."
            )
        ambiguity_uncertainty = None
    else:
        base_points = 0.14 if destination_candidates == 2 else 0.06
        history_points = min(history_confirmations * 0.02, 0.08)
        ambiguity_points = round(min(base_points + history_points, 0.25), 4)
        ambiguity_explanation = (
            f"{destination_candidates} compatible destinations remain. "
            f"{history_confirmations} prior human confirmation"
            f"{'s' if history_confirmations != 1 else ''} favor this target; history "
            "reduces only target ambiguity and does not verify the current value."
        )
        ambiguity_uncertainty = (
            f"The mapping still has {destination_candidates - 1} competing destination"
            f"{'s' if destination_candidates - 1 != 1 else ''}."
        )
    ambiguity_factor = _factor(
        code="destination_ambiguity",
        label="Destination ambiguity",
        awarded=ambiguity_points,
        maximum=0.25,
        explanation=ambiguity_explanation,
        uncertainty=ambiguity_uncertainty,
    )

    if corroborating_sources == 0:
        corroboration_points = 0.0
        corroboration_explanation = (
            "No additional independent source confirms the current value. Prior mapping "
            "history is deliberately excluded from this factor."
        )
        corroboration_uncertainty = (
            "The current value appears in only one source and is not corroborated."
        )
    elif corroborating_sources == 1:
        corroboration_points = 0.10
        corroboration_explanation = (
            "One additional independent source confirms the current value. Prior mapping "
            "history is deliberately excluded from this factor."
        )
        corroboration_uncertainty = "Only one additional source corroborates the current value."
    else:
        corroboration_points = 0.15
        corroboration_explanation = (
            f"{corroborating_sources} additional independent sources confirm the current "
            "value. Prior mapping history is deliberately excluded from this factor."
        )
        corroboration_uncertainty = None
    corroboration_factor = _factor(
        code="independent_corroboration",
        label="Independent corroboration",
        awarded=corroboration_points,
        maximum=0.15,
        explanation=corroboration_explanation,
        uncertainty=corroboration_uncertainty,
    )

    factors = (
        source_factor,
        format_factor,
        semantic_factor,
        ambiguity_factor,
        corroboration_factor,
    )
    remaining_uncertainty = tuple(
        factor.uncertainty
        for factor in factors
        if factor.awarded < factor.maximum and factor.uncertainty
    )
    return ConfidenceAssessment(
        score=round(sum(factor.awarded for factor in factors), 4),
        factors=factors,
        remaining_uncertainty=remaining_uncertainty,
    )
