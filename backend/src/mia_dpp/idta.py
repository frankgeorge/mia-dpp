"""Python port of the current local Digital Nameplate demo logic."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from re import Pattern

from mia_dpp.models import DemoProposal, DppPackage, FieldMapping, MappingDraft, MappingStatus


@dataclass(frozen=True)
class NameplateElement:
    name: str
    semantic_id: str
    hint: str
    required: bool = False


NAMEPLATE_ELEMENTS = (
    NameplateElement(
        "ManufacturerName",
        "0173-1#02-AAO677#002",
        "Legal name of the company that made the product",
        True,
    ),
    NameplateElement(
        "ManufacturerProductDesignation",
        "0173-1#02-AAW338#001",
        "Product name or model designation",
        True,
    ),
    NameplateElement(
        "ManufacturerProductFamily",
        "0173-1#02-AAU731#001",
        "Product family or series the item belongs to",
    ),
    NameplateElement(
        "SerialNumber",
        "0173-1#02-AAM556#002",
        "Unique serial number of the individual item",
        True,
    ),
    NameplateElement(
        "YearOfConstruction",
        "0173-1#02-AAP906#001",
        "Year the product was built",
        True,
    ),
    NameplateElement(
        "CountryOfOrigin",
        "0173-1#02-AAO259#004",
        "Country where the product was manufactured",
    ),
    NameplateElement(
        "ManufacturingSite",
        "0173-1#02-AAW336#001",
        "Plant or site where the product was manufactured",
    ),
    NameplateElement(
        "OrderCode",
        "0173-1#02-AAO227#002",
        "Article, order or material number used to order the product",
    ),
    NameplateElement(
        "DegreeOfProtection",
        "0173-1#02-AAM634#003",
        "IP rating or ingress protection class",
    ),
    NameplateElement(
        "MeasuringRange",
        "0173-1#02-AAN401#003",
        "Operating or measuring range, with unit",
    ),
    NameplateElement(
        "MaterialNumber",
        "0173-1#02-AAO676#003",
        "Internal material master number",
    ),
    NameplateElement(
        "CEMarking",
        "0173-1#02-AAO729#001",
        "CE conformity marking or declared conformity",
    ),
)

REQUIRED_ELEMENTS = tuple(element.name for element in NAMEPLATE_ELEMENTS if element.required)
UNKNOWN_SEMANTIC_ID = "0173-1#02-XXXXXX#001"


def semantic_id_for(element_name: str) -> str:
    """Return the current demo's semantic ID, including its unknown placeholder."""

    normalized = element_name.casefold()
    return next(
        (
            element.semantic_id
            for element in NAMEPLATE_ELEMENTS
            if element.name.casefold() == normalized
        ),
        UNKNOWN_SEMANTIC_ID,
    )


def missing_required(mappings: list[FieldMapping]) -> list[str]:
    """List required elements not represented by an accepted mapping."""

    accepted = {
        mapping.target_element
        for mapping in mappings
        if mapping.status in {MappingStatus.AUTO, MappingStatus.APPROVED}
    }
    return [element for element in REQUIRED_ELEMENTS if element not in accepted]


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:40]
    return slug or "product"


def _base36(value: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    result = ""
    while value:
        value, remainder = divmod(value, 36)
        result = digits[remainder] + result
    return result or "0"


def build_dpp(
    product_name: str,
    mappings: list[FieldMapping],
    *,
    now: datetime | None = None,
) -> DppPackage:
    """Build the same AAS-shaped object currently produced by TypeScript."""

    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    moment = moment.astimezone(UTC)
    timestamp_ms = int(moment.timestamp() * 1000)
    passport_id = f"urn:dpp:{_slug(product_name)}:{_base36(timestamp_ms)}"
    approved = [
        mapping
        for mapping in mappings
        if mapping.status in {MappingStatus.AUTO, MappingStatus.APPROVED}
    ]

    submodel_elements = []
    for mapping in approved:
        submodel_elements.append(
            {
                "idShort": mapping.target_element,
                "modelType": "Property",
                "valueType": "xs:string",
                "value": mapping.source_value,
                "semanticId": {
                    "type": "ExternalReference",
                    "keys": [{"type": "GlobalReference", "value": mapping.semantic_id}],
                },
                "qualifiers": [
                    {
                        "type": "MappingConfidence",
                        "valueType": "xs:double",
                        "value": f"{mapping.confidence:.2f}",
                    },
                    {
                        "type": "SourceField",
                        "valueType": "xs:string",
                        "value": mapping.source_field,
                    },
                ],
            }
        )

    generated_at = moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return DppPackage(
        product_name=product_name,
        passport_id=passport_id,
        generated_at=generated_at,
        submodel={
            "idShort": "Nameplate",
            "id": passport_id,
            "kind": "Instance",
            "semanticId": {
                "type": "ExternalReference",
                "keys": [
                    {
                        "type": "GlobalReference",
                        "value": "https://admin-shell.io/zvei/nameplate/2/0/Nameplate",
                    }
                ],
            },
            "modelType": "Submodel",
            "submodelElements": submodel_elements,
        },
    )


@dataclass(frozen=True)
class PatternRule:
    pattern: Pattern[str]
    source: str
    target: str
    confidence: float
    reasoning: str


PATTERNS = (
    PatternRule(
        re.compile(
            r"\b(?:serial(?:\s*(?:no|number|nr))?|sn|seriennummer)\b[:\s#]*"
            r"([A-Za-z0-9][A-Za-z0-9\-/]{2,})",
            re.IGNORECASE,
        ),
        "SERNR",
        "SerialNumber",
        0.96,
        "Explicit serial-number label with an alphanumeric identifier.",
    ),
    PatternRule(
        re.compile(r"\b(IP\s?\d{2})\b", re.IGNORECASE),
        "SCHUTZART",
        "DegreeOfProtection",
        0.94,
        "Matches the IPxx ingress-protection notation.",
    ),
    PatternRule(
        re.compile(
            r"\b(\d+(?:[.,]\d+)?\s*(?:-|to|bis|\u2013)\s*\d+(?:[.,]\d+)?\s*"
            r"(?:bar|mbar|°C|psi|kPa|MPa|V|A))\b",
            re.IGNORECASE,
        ),
        "MESSBEREICH",
        "MeasuringRange",
        0.88,
        "Numeric span followed by a physical unit reads as a range.",
    ),
    PatternRule(
        re.compile(
            r"\b(?:model|modell|type|typ|designation)\b[:\s]*"
            r"([A-Za-z0-9][A-Za-z0-9.-]{1,})",
            re.IGNORECASE,
        ),
        "MATNR_TXT",
        "ManufacturerProductDesignation",
        0.91,
        "Labelled model/type designation.",
    ),
    PatternRule(
        re.compile(
            r"\b(?:made in|manufactured in|hergestellt in)\s+"
            r"([A-Za-zÄÖÜäöüß\s]{3,25})",
            re.IGNORECASE,
        ),
        "LAND1",
        "CountryOfOrigin",
        0.90,
        "Country stated with an origin phrase.",
    ),
    PatternRule(
        re.compile(
            r"\b(?:plant|werk|site|factory)\b[:\s]*"
            r"([A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\-\s]{2,24})",
            re.IGNORECASE,
        ),
        "WERKS",
        "ManufacturingSite",
        0.86,
        "SAP plant code WERKS conventionally carries the manufacturing site.",
    ),
    PatternRule(
        re.compile(
            r"\b(?:material(?:\s*(?:no|nr|number))?|matnr|"
            r"article(?:\s*(?:no|nr|number))?|art\.?\s?nr|order\s*code)"
            r"\b[:\s#.]*([A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)*)",
            re.IGNORECASE,
        ),
        "MATNR",
        "OrderCode",
        0.79,
        "Material number is often reused as the order code, but the two can diverge.",
    ),
    PatternRule(
        re.compile(
            r"\b(?:year|baujahr|built|year of construction)\b[:\s]*((?:19|20)\d{2})",
            re.IGNORECASE,
        ),
        "BAUJAHR",
        "YearOfConstruction",
        0.93,
        "Four-digit year with a construction-year label.",
    ),
    PatternRule(
        re.compile(r"\b(CE)\b[\s-]*(?:mark|marking|konform)?", re.IGNORECASE),
        "CE_KZ",
        "CEMarking",
        0.72,
        "CE mentioned, but the declaration reference is not stated.",
    ),
)

KNOWN_MANUFACTURERS = ("AFRISO", "SCHUNK", "FIBRO", "Bosch", "Siemens", "Festo")


def demo_propose(text: str) -> DemoProposal:
    """Port the current no-API-key proposal behavior to Python."""

    found: list[MappingDraft] = []
    seen: set[str] = set()

    def add(mapping: MappingDraft) -> None:
        if mapping.target_element not in seen:
            seen.add(mapping.target_element)
            found.append(mapping)

    manufacturer = next(
        (
            name
            for name in KNOWN_MANUFACTURERS
            if re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE)
        ),
        None,
    )
    if manufacturer:
        add(
            MappingDraft(
                source_field="NAME1",
                source_value=manufacturer,
                target_element="ManufacturerName",
                semantic_id=semantic_id_for("ManufacturerName"),
                confidence=0.97,
                reasoning="Recognised manufacturer name stated directly in the request.",
            )
        )

    for rule in PATTERNS:
        if match := rule.pattern.search(text):
            add(
                MappingDraft(
                    source_field=rule.source,
                    source_value=(match.group(1) or match.group(0)).strip(),
                    target_element=rule.target,
                    semantic_id=semantic_id_for(rule.target),
                    confidence=rule.confidence,
                    reasoning=rule.reasoning,
                )
            )

    if "YearOfConstruction" not in seen:
        if year := re.search(r"\b(19[89]\d|20[0-4]\d)\b", text):
            add(
                MappingDraft(
                    source_field="BAUJAHR",
                    source_value=year.group(1),
                    target_element="YearOfConstruction",
                    semantic_id=semantic_id_for("YearOfConstruction"),
                    confidence=0.64,
                    reasoning=(
                        "Unlabelled four-digit year. Could also be a revision or catalogue year, "
                        "so this needs a human check."
                    ),
                )
            )

    designation = next(
        (
            mapping.source_value
            for mapping in found
            if mapping.target_element == "ManufacturerProductDesignation"
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
    product_name = (designation or fallback or "Product")[:60]
    return DemoProposal(product_name=product_name, mappings=tuple(found))
