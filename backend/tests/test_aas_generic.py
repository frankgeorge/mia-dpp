"""Prove the compiler is template-driven rather than Nameplate-specific."""

from datetime import UTC, datetime

from aas_core3 import jsonization, verification

from mia_dpp.aas import AasCompiler, AasValidator
from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.domain.evidence import (
    EvidenceRecord,
    EvidenceStatus,
    ProductKnowledgePackage,
    SourceLocation,
)
from mia_dpp.domain.mappings import FieldMapping, MappingStatus
from mia_dpp.tools.mapping.confidence import (
    MatchQuality,
    ValueFormatQuality,
    assess_mapping,
)
from mia_dpp.tools.mapping.targets import mapping_target


def test_compiles_nested_technical_data_from_the_second_official_template() -> None:
    repository = OfficialTemplateRepository()
    template = repository.load("technical_data")
    values = {
        "ManufacturerName": "MIA Manufacturing GmbH",
        "ManufacturerProductDesignation": "PG-16",
        "ManufacturerArticleNumber": "63820",
        "ManufacturerOrderCode": "PG16-ORDER",
    }
    assessment = assess_mapping(
        source_label=MatchQuality.EXACT,
        value_format=ValueFormatQuality.VALID,
        semantic_match=MatchQuality.EXACT,
        destination_candidates=1,
    )
    acquired_at = datetime(2026, 1, 1, tzinfo=UTC)
    evidence = tuple(
        EvidenceRecord(
            id=f"ev-{index}",
            predicate=f"technical.{name.casefold()}",
            value=value,
            source_uri="urn:test:technical-data",
            source_content_sha256="0" * 64,
            source_location=SourceLocation(excerpt=value),
            extraction_method="test",
            extractor_name="test",
            extractor_version="1",
            status=EvidenceStatus.VERIFIED,
            acquired_at=acquired_at,
        )
        for index, (name, value) in enumerate(values.items())
    )
    package = ProductKnowledgePackage(
        product_id="pg-16",
        product_name="PG-16",
        evidence=evidence,
    )
    mappings = tuple(
        FieldMapping(
            id=f"mapping-{record.id}",
            evidence_id=record.id,
            source_field=name,
            source_value=str(record.value),
            target=mapping_target(
                template,
                ("TechnicalData", "GeneralInformation", name),
            ),
            assessment=assessment,
            reasoning="Exact fixture mapping.",
            status=MappingStatus.AUTO,
        )
        for record, name in zip(evidence, values, strict=True)
    )

    artifact = AasCompiler(repository).compile(package, mappings, template)
    report = AasValidator().validate(artifact, template, mappings)

    environment = jsonization.environment_from_jsonable(artifact.environment)
    assert list(verification.verify(environment)) == []
    assert report.valid
    general = artifact.submodel["submodelElements"][0]
    assert general["idShort"] == "GeneralInformation"
    assert [item["idShort"] for item in general["value"]] == list(values)
