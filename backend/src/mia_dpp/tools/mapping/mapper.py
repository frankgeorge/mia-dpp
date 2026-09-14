"""Downstream website evidence mapping; extraction never imports this module."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import ClassVar

from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.domain.evidence import EvidenceRecord
from mia_dpp.domain.mappings import MappingResult, MappingStatus, ProposedFieldMapping
from mia_dpp.tools.mapping.confidence import (
    MatchQuality,
    ValueFormatQuality,
    assess_mapping,
)
from mia_dpp.tools.mapping.targets import mapping_target
from mia_dpp.tools.mapping.text_mapping import propose_text_mappings

MappingHistory = Mapping[tuple[str, str], int]


class DeterministicWebsiteMapper:
    """Propose evidence-to-target mappings from deterministic rules.

    Resolution calls this after evidence exists. Recognized facts become
    automatic or review mappings; every other evidence ID remains unmatched.
    """

    _LABEL_ALIASES: ClassVar[dict[str, str]] = {
        "brand": "manufacturer",
        "manufacturer": "manufacturer",
        "model": "model",
        "designation": "designation",
        "product designation": "designation",
        "serial number": "serial number",
        "sku": "order code",
        "mpn": "order code",
        "order code": "order code",
        "order number": "order code",
        "article number": "article number",
        "year of construction": "year of construction",
        "country of origin": "made in",
    }

    def __init__(self, repository: OfficialTemplateRepository) -> None:
        self._repository = repository

    async def propose(
        self,
        evidence: Sequence[EvidenceRecord],
        *,
        history: MappingHistory,
    ) -> MappingResult:
        """Map each evidence record once and return mapped, ambiguous, and unmatched sets."""

        mapped: list[ProposedFieldMapping] = []
        ambiguous: list[ProposedFieldMapping] = []
        unmatched: list[str] = []
        claimed_targets: set[tuple[str, ...]] = set()

        for record in evidence:
            label = record.source_label or record.predicate
            if label.casefold() == "product page url":
                target = mapping_target(
                    self._repository.load("digital_nameplate"),
                    ("Nameplate", "URIOfTheProduct"),
                )
                assessment = assess_mapping(
                    source_label=MatchQuality.EXACT,
                    value_format=ValueFormatQuality.VALID,
                    semantic_match=MatchQuality.EXACT,
                    destination_candidates=1,
                )
                mapped.append(
                    ProposedFieldMapping(
                        evidence_id=record.id,
                        source_field=label,
                        source_value=str(record.value),
                        target_element=target.id_short,
                        semantic_id=target.semantic_id.primary_value,
                        target=target,
                        assessment=assessment,
                        reasoning=(
                            "The acquired public product-page URL supplies the official product "
                            "URI field directly."
                        ),
                        status=MappingStatus.AUTO,
                    )
                )
                claimed_targets.add(target.instance_path)
                continue
            mapping_label = self._LABEL_ALIASES.get(label.casefold())
            value = str(record.value)
            draft = propose_text_mappings(
                f"{mapping_label}: {value}" if mapping_label else value,
                self._repository,
                history=dict(history),
                allow_unlabelled_year=False,
            )
            candidates = [
                item
                for item in draft.mappings
                if self._same_value(item.source_value, value)
                and item.target.instance_path not in claimed_targets
            ]
            if not candidates:
                unmatched.append(record.id)
                continue

            candidate = candidates[0]
            claimed_targets.add(candidate.target.instance_path)
            has_competing_destination = any(
                "target destinations remain" in item
                for item in candidate.assessment.uncertainties
            )
            proposal = ProposedFieldMapping(
                **candidate.model_copy(
                    update={
                        "evidence_id": record.id,
                        "source_field": label,
                        "source_value": value,
                    }
                ).model_dump(),
                status=(
                    MappingStatus.REVIEW
                    if has_competing_destination
                    else (
                        MappingStatus.REVIEW
                        if candidate.assessment.review_required
                        else MappingStatus.AUTO
                    )
                ),
            )
            (ambiguous if has_competing_destination else mapped).append(proposal)

        return MappingResult(
            mapped=tuple(mapped),
            ambiguous=tuple(ambiguous),
            unmatched_evidence_ids=tuple(unmatched),
        )

    @staticmethod
    def _same_value(candidate: str, evidence: str) -> bool:
        return " ".join(candidate.split()).casefold() == " ".join(evidence.split()).casefold()
