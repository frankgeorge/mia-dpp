"""End-to-end tests for the deterministic official-template pipeline."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aas_core3 import jsonization, verification

from mia_dpp.aas.build import build_dpp
from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.domain.mappings import FieldMapping, MappingStatus, MappingTarget
from mia_dpp.errors import MappingError
from mia_dpp.tools.mapping.targets import external_reference
from mia_dpp.tools.mapping.text_mapping import propose_text_mappings

PRODUCT = (
    "AFRISO gauge, model RF100-16, serial number 2024-8871, built 2024, "
    "IP65, 0-16 bar, material number 63820."
)


def accepted_mappings(text: str = PRODUCT) -> tuple[str, list[FieldMapping]]:
    proposal = propose_text_mappings(text, OfficialTemplateRepository())
    mappings = [
        mapping.model_copy(update={"id": f"mapping-{index}", "status": MappingStatus.APPROVED})
        for index, mapping in enumerate(proposal.mappings)
    ]
    return proposal.product_name, mappings


def test_text_mapping_uses_official_and_wildcard_template_paths() -> None:
    proposal = propose_text_mappings(PRODUCT, OfficialTemplateRepository())

    targets = {item.target.id_short: item.target for item in proposal.mappings}
    assert proposal.product_name == "RF100-16"
    assert targets["ManufacturerName"].template_release == "3.0.1"
    assert targets["ManufacturerName"].semantic_id.primary_value == ("0112/2///61987#ABA565#009")
    assert targets["OrderCodeOfManufacturer"].template_path == (
        "Nameplate",
        "OrderCodeOfManufacturer",
    )
    assert targets["DegreeOfProtection"].template_path == (
        "Nameplate",
        "AssetSpecificProperties",
        "ArbitraryProperty",
    )
    assert targets["DegreeOfProtection"].instance_path[-1] == "DegreeOfProtection"
    assert all(item.evidence_id.startswith("ev-") for item in proposal.mappings)


def test_pipeline_builds_a_repeatable_aas_core_verified_environment() -> None:
    product_name, mappings = accepted_mappings()
    repository = OfficialTemplateRepository()
    first = build_dpp(
        product_name,
        mappings,
        repository=repository,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )
    second = build_dpp(
        product_name,
        list(reversed(mappings)),
        repository=repository,
        now=datetime(2027, 2, 3, tzinfo=UTC),
    )

    environment = jsonization.environment_from_jsonable(first.environment)
    assert list(verification.verify(environment)) == []
    assert first.artifact_sha256 == second.artifact_sha256
    assert first.environment == second.environment
    assert first.generated_at != second.generated_at
    assert first.deployable
    assert first.validation_report.valid
    assert first.validation_report.findings[0].code == "IDTA-EXTERNAL-DROPIN"
    elements = {item["idShort"]: item for item in first.submodel["submodelElements"]}
    assert elements["ManufacturerName"]["modelType"] == "MultiLanguageProperty"
    assert elements["ManufacturerName"]["value"] == [{"language": "en", "text": "AFRISO"}]
    assert elements["URIOfTheProduct"]["value"].startswith("urn:mia:asset:")


def test_missing_required_template_elements_are_reported_and_block_deployment() -> None:
    product_name, mappings = accepted_mappings(
        "SCHUNK clamping module, order code JGZ-100-1, 2022."
    )

    package = build_dpp(
        product_name,
        mappings,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )

    assert not package.deployable
    assert not package.validation_report.valid
    assert package.gap_report.blocks_deployment
    assert [gap.template_path for gap in package.gap_report.gaps] == [
        ("Nameplate", "ManufacturerProductDesignation")
    ]


def test_client_cannot_replace_an_official_fixed_semantic_id() -> None:
    product_name, mappings = accepted_mappings()
    original = mappings[0]
    forged_reference = external_reference("https://attacker.example/not-idta")
    target_data = original.target.model_dump(by_alias=False)
    target_data["semantic_id"] = forged_reference
    forged_target = MappingTarget(**target_data)
    mapping_data = original.model_dump(exclude={"target"})
    forged = FieldMapping(
        **mapping_data,
        target=forged_target,
    )

    with pytest.raises(MappingError, match="semantic ID differs"):
        build_dpp(product_name, [forged])


def test_rejected_and_pending_mappings_do_not_enter_the_artifact() -> None:
    product_name, mappings = accepted_mappings()
    mappings[0] = mappings[0].model_copy(update={"status": MappingStatus.REJECTED})
    mappings[1] = mappings[1].model_copy(update={"status": MappingStatus.REVIEW})

    package = build_dpp(product_name, mappings)

    rendered = str(package.environment)
    assert mappings[0].source_value not in rendered
    assert mappings[1].source_value not in rendered
