from __future__ import annotations

from pathlib import Path

import pytest

from mia_dpp.models import Cardinality
from mia_dpp.templates import (
    DIGITAL_NAMEPLATE,
    STANDARDS_REPOSITORY_COMMIT,
    TECHNICAL_DATA,
    OfficialTemplateRepository,
    StandardsSubmoduleMissingError,
    TemplateElementNotFoundError,
    TemplateIntegrityError,
    UnknownTemplateError,
    resolve_semantic_id,
)


def test_catalog_pins_exact_official_artifacts() -> None:
    assert STANDARDS_REPOSITORY_COMMIT == "a9664731a903b29ac5f45e23ab3a25c581f3d92f"
    assert DIGITAL_NAMEPLATE.release == "3.0.1"
    assert DIGITAL_NAMEPLATE.source_path.endswith(
        "3/0/1/IDTA 02006-3-0-1_Template_Digital Nameplate.json"
    )
    assert (
        DIGITAL_NAMEPLATE.source_sha256
        == "c2358c18c1d908f943aba76575aec19bb010454d78389ca6bd43f0e5dbae025c"
    )
    assert TECHNICAL_DATA.release == "2.0.1"
    assert TECHNICAL_DATA.source_path.endswith("2/0/1/IDTA 02003_2-0-1_Template_TechnicalData.json")
    assert (
        TECHNICAL_DATA.source_sha256
        == "97aac6192b2657e4a03a2204ecd167494252129b03e58838453e3f1d0abefb6a"
    )


def test_nameplate_is_normalized_from_the_official_json() -> None:
    repository = OfficialTemplateRepository()

    template = repository.load("digital_nameplate")
    summary = repository.summary("digital_nameplate")
    manufacturer = repository.resolve("digital_nameplate", "Nameplate/ManufacturerName")

    assert template.id_short == "Nameplate"
    assert template.administration_version == "3"
    assert template.administration_revision == "0"
    assert template.template_id == "https://admin-shell.io/idta-02006-3-0"
    assert template.semantic_id.primary_value == (
        "https://admin-shell.io/idta/nameplate/3/0/Nameplate"
    )
    assert summary.element_count == 36
    assert manufacturer.model_type == "MultiLanguageProperty"
    assert manufacturer.cardinality is Cardinality.ONE
    assert manufacturer.description
    assert manufacturer.semantic_id is not None
    assert manufacturer.semantic_id.primary_value == "0112/2///61987#ABA565#009"
    assert manufacturer.supplemental_semantic_ids[0].primary_value == ("0173-1#02-AAO677#004")


def test_list_prototypes_get_stable_paths_and_keep_list_constraints() -> None:
    repository = OfficialTemplateRepository()

    markings = repository.resolve("digital_nameplate", ("Nameplate", "Markings"))
    prototype = repository.resolve("digital_nameplate", "Nameplate/Markings/[]")
    marking_name = repository.resolve("digital_nameplate", "Nameplate/Markings/[]/MarkingName")

    assert markings.model_type == "SubmodelElementList"
    assert markings.type_value_list_element == "SubmodelElementCollection"
    assert markings.cardinality is Cardinality.ZERO_TO_ONE
    assert prototype.id_short is None
    assert prototype.path == ("Nameplate", "Markings", "[]")
    assert prototype.cardinality is Cardinality.ONE_TO_MANY
    assert marking_name.source_pointer.endswith("/value/0/value/0")


def test_technical_data_keeps_arbitrary_extension_points() -> None:
    repository = OfficialTemplateRepository()
    template = repository.load("technical_data")

    arbitrary = repository.resolve(
        "technical_data",
        "TechnicalData/TechnicalPropertyAreas/[]/ArbitraryProperty",
    )
    semantic_matches = resolve_semantic_id(template, "https://admin-shell.io/SMT/General/Arbitrary")

    assert repository.summary("technical_data").element_count == 62
    assert arbitrary.wildcard is True
    assert arbitrary.cardinality is Cardinality.ZERO_TO_MANY
    assert arbitrary.model_type == "Property"
    assert len(semantic_matches) > 1


def test_raw_documents_are_defensive_copies() -> None:
    repository = OfficialTemplateRepository()

    first_document = repository.load_document("digital_nameplate")
    first_submodel = repository.raw_submodel("digital_nameplate")
    first_document["submodels"][0]["idShort"] = "Changed"
    first_submodel["idShort"] = "AlsoChanged"

    assert repository.raw_submodel("digital_nameplate")["idShort"] == "Nameplate"


def test_repository_errors_are_actionable(tmp_path: Path) -> None:
    missing = OfficialTemplateRepository(tmp_path / "not-initialized")
    with pytest.raises(StandardsSubmoduleMissingError, match="git submodule update --init"):
        missing.load("digital_nameplate")

    with pytest.raises(UnknownTemplateError, match="available templates"):
        OfficialTemplateRepository().get("unknown")

    repository = OfficialTemplateRepository()
    template = repository.load("digital_nameplate")
    with pytest.raises(TemplateElementNotFoundError, match="NoSuchElement"):
        repository.resolve("digital_nameplate", "Nameplate/NoSuchElement")
    assert template.id_short == "Nameplate"


def test_modified_template_fails_before_parsing(tmp_path: Path) -> None:
    release = DIGITAL_NAMEPLATE
    source = tmp_path / release.source_path
    source.parent.mkdir(parents=True)
    source.write_text("{}", encoding="utf-8")

    with pytest.raises(TemplateIntegrityError, match="SHA-256"):
        OfficialTemplateRepository(tmp_path).load(release.key)
