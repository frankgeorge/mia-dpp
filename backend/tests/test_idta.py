"""Behavior examples for the TypeScript logic ported to Python."""

from datetime import UTC, datetime

from mia_dpp.idta import build_dpp, demo_propose, missing_required
from mia_dpp.models import FieldMapping, MappingStatus


def mapping(target: str, status: MappingStatus) -> FieldMapping:
    return FieldMapping(
        id=target,
        source_field="SOURCE",
        source_value="value",
        target_element=target,
        semantic_id="semantic-id",
        confidence=0.9,
        reasoning="test mapping",
        status=status,
    )


def test_demo_proposes_the_current_pressure_gauge_fields() -> None:
    proposal = demo_propose(
        "Create a DPP for our AFRISO pressure gauge, model RF100-16, "
        "serial number 2024-8871, built 2024, IP65, range 0-16 bar, "
        "material number 63820."
    )

    assert proposal.product_name == "RF100-16"
    assert [item.target_element for item in proposal.mappings] == [
        "ManufacturerName",
        "SerialNumber",
        "DegreeOfProtection",
        "MeasuringRange",
        "ManufacturerProductDesignation",
        "OrderCode",
        "YearOfConstruction",
    ]


def test_only_accepted_mappings_enter_the_dpp() -> None:
    package = build_dpp(
        "Demo product",
        [
            mapping("ManufacturerName", MappingStatus.APPROVED),
            mapping("SerialNumber", MappingStatus.AUTO),
            mapping("YearOfConstruction", MappingStatus.REVIEW),
        ],
        now=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )

    elements = package.submodel["submodelElements"]
    assert [element["idShort"] for element in elements] == [
        "ManufacturerName",
        "SerialNumber",
    ]
    assert package.generated_at == "2026-01-02T03:04:05.000Z"
    assert package.passport_id == "urn:dpp:demo-product:mjwaid1k"


def test_missing_required_uses_the_current_acceptance_rule() -> None:
    assert missing_required([mapping("ManufacturerName", MappingStatus.APPROVED)]) == [
        "ManufacturerProductDesignation",
        "SerialNumber",
        "YearOfConstruction",
    ]
