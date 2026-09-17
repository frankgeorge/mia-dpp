"""Small deterministic policy explaining the basis for a mapping."""

from __future__ import annotations

from enum import StrEnum

from mia_dpp.domain.mappings import MappingAssessment, MappingBasis


class MatchQuality(StrEnum):
    """Strength assigned by an extractor or deterministic mapping rule."""

    NONE = "none"
    WEAK = "weak"
    STRONG = "strong"
    EXACT = "exact"


class ValueFormatQuality(StrEnum):
    """Result of validating a source value against a target format."""

    INVALID = "invalid"
    UNKNOWN = "unknown"
    PLAUSIBLE = "plausible"
    VALID = "valid"


def assess_mapping(
    *,
    source_label: MatchQuality,
    value_format: ValueFormatQuality,
    semantic_match: MatchQuality,
    destination_candidates: int,
) -> MappingAssessment:
    """Return a reproducible mapping basis and explicit review decision.

    Ambiguity or weak/incompatible signals always require a person; no
    pseudo-probability is calculated.
    """

    if destination_candidates < 1:
        raise ValueError("destination_candidates must be at least one")
    uncertainties: list[str] = []
    if destination_candidates > 1:
        uncertainties.append(f"{destination_candidates} compatible target destinations remain.")
    if source_label in {MatchQuality.NONE, MatchQuality.WEAK}:
        uncertainties.append("The source label does not identify the target exactly.")
    if value_format in {ValueFormatQuality.INVALID, ValueFormatQuality.UNKNOWN}:
        uncertainties.append("The source value has not passed the target format check.")
    if semantic_match in {MatchQuality.NONE, MatchQuality.WEAK}:
        uncertainties.append("The semantic relationship is not strong enough to accept.")

    return MappingAssessment(
        basis=MappingBasis.EXACT,
        review_required=bool(uncertainties),
        reason="A deterministic rule matched one official target with compatible evidence.",
        uncertainties=tuple(uncertainties),
    )
