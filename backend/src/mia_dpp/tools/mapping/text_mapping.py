"""Deterministic regex-based text evidence and mapping proposals.

This module keeps the original demo useful while changing its foundation: the
regexes extract evidence, but all target metadata comes from the pinned
official template repository.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from re import Pattern

from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.domain.evidence import EvidenceRecord, EvidenceStatus, SourceLocation
from mia_dpp.domain.mappings import MappingDraft, MappingTarget, TextMappingProposal
from mia_dpp.tools.mapping.confidence import (
    MatchQuality,
    ValueFormatQuality,
    assess_mapping,
)
from mia_dpp.tools.mapping.targets import ARBITRARY_PROPERTY_PATH, NAMEPLATE_ROOT, mapping_target


@dataclass(frozen=True, slots=True)
class PatternRule:
    pattern: Pattern[str]
    source_field: str
    predicate: str
    template_path: tuple[str, ...]
    reasoning: str
    source_label: MatchQuality = MatchQuality.EXACT
    value_format: ValueFormatQuality = ValueFormatQuality.VALID
    semantic_match: MatchQuality = MatchQuality.EXACT
    destination_candidates: int = 1
    instance_id_short: str | None = None
    semantic_id_override: str | None = None


PATTERNS = (
    PatternRule(
        re.compile(
            r"\b(?:serial(?:\s*(?:no|number|nr))?|sn|seriennummer)\b[:\s#]*"
            r"([A-Za-z0-9][A-Za-z0-9\-/]{2,})",
            re.IGNORECASE,
        ),
        "SERNR",
        "product.serial_number",
        (NAMEPLATE_ROOT, "SerialNumber"),
        "An explicit serial-number label identifies the individual product.",
    ),
    PatternRule(
        re.compile(r"\b(IP\s?\d{2})\b", re.IGNORECASE),
        "SCHUTZART",
        "product.degree_of_protection",
        ARBITRARY_PROPERTY_PATH,
        "The value follows the standard IPxx protection notation.",
        semantic_match=MatchQuality.STRONG,
        instance_id_short="DegreeOfProtection",
        semantic_id_override="0173-1#02-AAM634#003",
    ),
    PatternRule(
        re.compile(
            r"\b(\d+(?:[.,]\d+)?\s*(?:-|to|bis|\u2013)\s*\d+(?:[.,]\d+)?\s*"
            r"(?:bar|mbar|°C|psi|kPa|MPa|V|A))\b",
            re.IGNORECASE,
        ),
        "MESSBEREICH",
        "product.measuring_range",
        ARBITRARY_PROPERTY_PATH,
        "A numeric span and physical unit identify a measuring range.",
        semantic_match=MatchQuality.STRONG,
        instance_id_short="MeasuringRange",
        semantic_id_override="0173-1#02-AAN401#003",
    ),
    PatternRule(
        re.compile(
            r"\b(?:model|modell|type|typ|designation)\b[:\s]*"
            r"([A-Za-z0-9][A-Za-z0-9.-]{1,})",
            re.IGNORECASE,
        ),
        "MATNR_TXT",
        "product.designation",
        (NAMEPLATE_ROOT, "ManufacturerProductDesignation"),
        "An explicit model/type label identifies the manufacturer's designation.",
    ),
    PatternRule(
        re.compile(
            r"\b(?:made in|manufactured in|hergestellt in)\b[:\s]+"
            r"([A-Za-zÄÖÜäöüß ]{2,25})",
            re.IGNORECASE,
        ),
        "LAND1",
        "product.country_of_origin",
        (NAMEPLATE_ROOT, "CountryOfOrigin"),
        "An origin phrase explicitly states the country of manufacture.",
    ),
    PatternRule(
        re.compile(
            r"\b(?:plant|werk)\b[:\s]*"
            r"([A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\- ]{2,24})",
            re.IGNORECASE,
        ),
        "WERKS",
        "product.manufacturing_site",
        ARBITRARY_PROPERTY_PATH,
        "A plant/site label identifies a manufacturing location.",
        semantic_match=MatchQuality.STRONG,
        instance_id_short="ManufacturingSite",
        semantic_id_override="0173-1#02-AAW336#001",
    ),
    PatternRule(
        re.compile(
            r"\b(?:material(?:\s*(?:no|nr|number))?|matnr|"
            r"article(?:\s*(?:no|nr|number))?|art\.?\s?nr|order\s*code)"
            r"\b[:\s#.]*([A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)*)",
            re.IGNORECASE,
        ),
        "MATNR",
        "product.order_code",
        (NAMEPLATE_ROOT, "OrderCodeOfManufacturer"),
        "The label identifies an order/article number, but those identifiers can diverge.",
        semantic_match=MatchQuality.STRONG,
        destination_candidates=2,
    ),
    PatternRule(
        re.compile(
            r"\b(?:year|baujahr|built|year of construction)\b[:\s]*((?:19|20)\d{2})",
            re.IGNORECASE,
        ),
        "BAUJAHR",
        "product.year_of_construction",
        (NAMEPLATE_ROOT, "YearOfConstruction"),
        "A construction-year label is followed by a valid four-digit year.",
    ),
    PatternRule(
        re.compile(r"\b(CE)\b[\s-]*(?:mark|marking|konform)?", re.IGNORECASE),
        "CE_KZ",
        "product.marking",
        (NAMEPLATE_ROOT, "Markings", "[]", "MarkingName"),
        "CE is present, although no certificate or declaration reference was supplied.",
        source_label=MatchQuality.STRONG,
        value_format=ValueFormatQuality.PLAUSIBLE,
        semantic_match=MatchQuality.STRONG,
        destination_candidates=2,
    ),
)

KNOWN_MANUFACTURERS = ("AFRISO", "SCHUNK", "FIBRO", "Bosch", "Siemens", "Festo")


def _evidence(
    *,
    text: str,
    source_field: str,
    predicate: str,
    value: str,
    excerpt: str,
) -> EvidenceRecord:
    content_hash = hashlib.sha256(text.encode()).hexdigest()
    identity = hashlib.sha256(
        f"{content_hash}\0{source_field}\0{predicate}\0{value}".encode()
    ).hexdigest()
    return EvidenceRecord(
        id=f"ev-{identity[:24]}",
        predicate=predicate,
        value=value,
        source_uri=f"urn:mia:manual:{content_hash[:24]}",
        source_content_sha256=content_hash,
        source_location=SourceLocation(excerpt=excerpt[:240]),
        extraction_method="deterministic_regex",
        extractor_name="mia-manual-text",
        extractor_version="2",
        status=EvidenceStatus.OBSERVED,
    )


def _draft(
    *,
    evidence: EvidenceRecord,
    source_field: str,
    target: MappingTarget,
    reasoning: str,
    source_label: MatchQuality,
    value_format: ValueFormatQuality,
    semantic_match: MatchQuality,
    destination_candidates: int,
) -> MappingDraft:
    assessment = assess_mapping(
        source_label=source_label,
        value_format=value_format,
        semantic_match=semantic_match,
        destination_candidates=destination_candidates,
    )
    return MappingDraft(
        evidence_id=evidence.id,
        source_field=source_field,
        source_value=str(evidence.value),
        target_element=target.id_short,
        semantic_id=target.semantic_id.primary_value,
        target=target,
        assessment=assessment,
        reasoning=reasoning,
    )


def propose_text_mappings(
    text: str,
    repository: OfficialTemplateRepository,
    *,
    allow_unlabelled_year: bool = True,
) -> TextMappingProposal:
    """Extract manual evidence and propose official-template mappings deterministically."""

    template = repository.load("digital_nameplate")
    evidence_records: list[EvidenceRecord] = []
    mappings: list[MappingDraft] = []
    seen_instance_paths: set[tuple[str, ...]] = set()

    def add(
        *,
        evidence: EvidenceRecord,
        source_field: str,
        target: MappingTarget,
        reasoning: str,
        source_label: MatchQuality,
        value_format: ValueFormatQuality,
        semantic_match: MatchQuality,
        destination_candidates: int,
    ) -> None:
        if target.instance_path in seen_instance_paths:
            return
        seen_instance_paths.add(target.instance_path)
        evidence_records.append(evidence)
        mappings.append(
            _draft(
                evidence=evidence,
                source_field=source_field,
                target=target,
                reasoning=reasoning,
                source_label=source_label,
                value_format=value_format,
                semantic_match=semantic_match,
                destination_candidates=destination_candidates,
            )
        )

    labelled_manufacturer = re.search(
        r"\b(?:manufacturer|brand|hersteller)\b[:\s-]+([^.;|\n]{2,80})",
        text,
        re.IGNORECASE,
    )
    manufacturer = (
        labelled_manufacturer.group(1).strip()
        if labelled_manufacturer
        else next(
            (
                name
                for name in KNOWN_MANUFACTURERS
                if re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE)
            ),
            None,
        )
    )
    if manufacturer:
        evidence = _evidence(
            text=text,
            source_field="NAME1",
            predicate="manufacturer.name",
            value=manufacturer,
            excerpt=manufacturer,
        )
        add(
            evidence=evidence,
            source_field="NAME1",
            target=mapping_target(template, (NAMEPLATE_ROOT, "ManufacturerName")),
            reasoning="A recognized manufacturer name appears directly in the source.",
            source_label=MatchQuality.STRONG,
            value_format=ValueFormatQuality.VALID,
            semantic_match=MatchQuality.EXACT,
            destination_candidates=1,
        )

    for rule in PATTERNS:
        match = rule.pattern.search(text)
        if match is None:
            continue
        value = (match.group(1) or match.group(0)).strip()
        evidence = _evidence(
            text=text,
            source_field=rule.source_field,
            predicate=rule.predicate,
            value=value,
            excerpt=match.group(0),
        )
        add(
            evidence=evidence,
            source_field=rule.source_field,
            target=mapping_target(
                template,
                rule.template_path,
                id_short=rule.instance_id_short,
                semantic_id=rule.semantic_id_override,
            ),
            reasoning=rule.reasoning,
            source_label=rule.source_label,
            value_format=rule.value_format,
            semantic_match=rule.semantic_match,
            destination_candidates=rule.destination_candidates,
        )

    if allow_unlabelled_year and not any(
        item.predicate == "product.year_of_construction" for item in evidence_records
    ):
        year = re.search(r"\b(19[89]\d|20[0-4]\d)\b", text)
        if year:
            evidence = _evidence(
                text=text,
                source_field="BAUJAHR",
                predicate="product.year_of_construction",
                value=year.group(1),
                excerpt=year.group(0),
            )
            add(
                evidence=evidence,
                source_field="BAUJAHR",
                target=mapping_target(template, (NAMEPLATE_ROOT, "YearOfConstruction")),
                reasoning=(
                    "An unlabelled four-digit year could be a construction, revision or "
                    "catalogue year."
                ),
                source_label=MatchQuality.NONE,
                value_format=ValueFormatQuality.VALID,
                semantic_match=MatchQuality.WEAK,
                destination_candidates=3,
            )

    designation = next(
        (
            item.source_value
            for item in mappings
            if item.target_element == "ManufacturerProductDesignation"
        ),
        None,
    )
    first_phrase = re.split(r"[.,\n]", text, maxsplit=1)[0]
    fallback = re.sub(
        r"^(create|make|build)\s+a?\s*dpp\s*(for)?\s*",
        "",
        first_phrase,
        flags=re.IGNORECASE,
    ).strip()
    return TextMappingProposal(
        product_name=(designation or fallback or "Product")[:60],
        evidence=tuple(evidence_records),
        mappings=tuple(mappings),
    )
