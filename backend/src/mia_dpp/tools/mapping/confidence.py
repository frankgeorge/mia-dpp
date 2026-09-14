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
    history_confirmations: int = 0,
) -> MappingAssessment:
    """Return a reproducible mapping basis and explicit review decision.

    Prior human confirmations establish a known relationship but never validate
    the current value. Ambiguity or weak/incompatible signals always require a
    person; no pseudo-probability is calculated.
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

    if history_confirmations:
        basis = MappingBasis.KNOWN
        reason = (
            f"This source-to-target relationship has {history_confirmations} prior human "
            "confirmation(s); the current value is still validated independently."
        )
    else:
        basis = MappingBasis.EXACT
        reason = "A deterministic rule matched one official target with compatible evidence."
    return MappingAssessment(
        basis=basis,
        review_required=bool(uncertainties),
        reason=reason,
        uncertainties=tuple(uncertainties),
    )
