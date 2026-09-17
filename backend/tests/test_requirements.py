from mia_dpp.aas.requirements import build_template_index
from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.domain.targets import Cardinality, Requirement, RequirementKind, TemplateIndex


def requirement_by_path(
    inventory: TemplateIndex,
    path: tuple[str, ...],
) -> Requirement:
    return next(item for item in inventory.requirements if item.template_path == path)


def test_builds_nameplate_requirements_from_normalized_official_elements() -> None:
    repository = OfficialTemplateRepository()
    inventory = build_template_index([repository.load("digital_nameplate")])

    manufacturer = requirement_by_path(inventory, ("Nameplate", "ManufacturerName"))
    family = requirement_by_path(inventory, ("Nameplate", "ManufacturerProductFamily"))
    address = requirement_by_path(inventory, ("Nameplate", "AddressInformation"))

    assert inventory.selected_templates == (repository.get("digital_nameplate"),)
    assert manufacturer.semantic_id is not None
    assert manufacturer.semantic_id.primary_value == "0112/2///61987#ABA565#009"
    assert manufacturer.model_type == "MultiLanguageProperty"
    assert manufacturer.cardinality is Cardinality.ONE
    assert manufacturer.required is True
    assert manufacturer.kind is RequirementKind.VALUE
    assert family.cardinality is Cardinality.ZERO_TO_ONE
    assert family.required is False
    assert address.kind is RequirementKind.STRUCTURAL
    assert address.required is True


def test_same_builder_handles_technical_data_and_conditional_children() -> None:
    repository = OfficialTemplateRepository()
    inventory = build_template_index([repository.load("technical_data")])

    manufacturer = requirement_by_path(
        inventory,
        ("TechnicalData", "GeneralInformation", "ManufacturerName"),
    )
    image = requirement_by_path(
        inventory,
        ("TechnicalData", "GeneralInformation", "ProductImages", "[]", "ImageFile"),
    )
    arbitrary = requirement_by_path(
        inventory,
        ("TechnicalData", "TechnicalPropertyAreas", "[]", "ArbitraryProperty"),
    )

    assert manufacturer.model_type == "Property"
    assert manufacturer.cardinality is Cardinality.ONE
    assert manufacturer.required is True
    assert image.cardinality is Cardinality.ONE
    assert image.required is False
    assert image.conditional is True
    assert arbitrary.kind is RequirementKind.VALUE
    assert arbitrary.wildcard is True
    assert arbitrary.cardinality is Cardinality.ZERO_TO_MANY


def test_combined_inventory_preserves_template_identity_and_unique_paths() -> None:
    repository = OfficialTemplateRepository()
    templates = [
        repository.load("digital_nameplate"),
        repository.load("technical_data"),
    ]
    inventory = build_template_index(templates)

    assert [item.key for item in inventory.selected_templates] == [
        "digital_nameplate",
        "technical_data",
    ]
    assert len(inventory.requirements) == 79
    assert len({item.id for item in inventory.requirements}) == 79
    qualified_paths = {
        (item.template_key, item.template_release, item.template_path)
        for item in inventory.requirements
    }
    assert len(qualified_paths) == 79

    manufacturers = [item for item in inventory.requirements if item.id_short == "ManufacturerName"]
    assert len(manufacturers) == 2
    assert len({item.id for item in manufacturers}) == 2
    assert {item.template_key for item in manufacturers} == {
        "digital_nameplate",
        "technical_data",
    }


def test_requirement_ids_are_stable_across_runs() -> None:
    repository = OfficialTemplateRepository()
    template = repository.load("technical_data")

    first = build_template_index([template])
    second = build_template_index([template])

    assert [item.id for item in first.requirements] == [item.id for item in second.requirements]
