"""Prove the compiler is template-driven rather than Nameplate-specific."""

from datetime import UTC, datetime

from aas_core3 import jsonization, verification

from mia_dpp.aas import AasCompiler, AasValidator
from mia_dpp.confidence import MatchQuality, ValueFormatQuality, assess_mapping_confidence
from mia_dpp.idta import mapping_target
from mia_dpp.models import (
    ApprovedMapping,
    EvidenceRecord,
    EvidenceStatus,
    MappingSpecification,
    ProductKnowledgePackage,
    SourceLocation,
    TargetProfile,
)
from mia_dpp.templates import OfficialTemplateRepository


def test_compiles_nested_technical_data_from_the_second_official_template() -> None:
    repository = OfficialTemplateRepository()
    template = repository.load("technical_data")
    values = {
        "ManufacturerName": "MIA Manufacturing GmbH",
        "ManufacturerProductDesignation": "PG-16",
        "ManufacturerArticleNumber": "63820",
        "ManufacturerOrderCode": "PG16-ORDER",
    }
    confidence = assess_mapping_confidence(
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
    profile = TargetProfile(
        id="technical-data-2-0-1",
        name="IDTA Technical Data 2.0.1",
        template=template.release,
    )
    mappings = tuple(
        ApprovedMapping(
            evidence_id=record.id,
            target=mapping_target(
                template,
                ("TechnicalData", "GeneralInformation", name),
            ),
            confidence_assessment=confidence,
        )
        for record, name in zip(evidence, values, strict=True)
    )
    specification = MappingSpecification(
        id="mapping-technical-data",
        target_profile=profile,
        mappings=mappings,
        approved_at=acquired_at,
    )

    artifact = AasCompiler(repository).compile(package, specification, template)
    report = AasValidator().validate(artifact, template, specification)

    environment = jsonization.environment_from_jsonable(artifact.environment)
    assert list(verification.verify(environment)) == []
    assert report.valid
    general = artifact.submodel["submodelElements"][0]
    assert general["idShort"] == "GeneralInformation"
    assert [item["idShort"] for item in general["value"]] == list(values)
