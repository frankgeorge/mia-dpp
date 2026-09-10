"""Application service composing evidence, reviewed mappings, compilation and validation."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from mia_dpp.aas import AasCompiler, AasValidator, gap_report_from_validation
from mia_dpp.errors import MappingError
from mia_dpp.models import (
    ApprovedMapping,
    DppPackage,
    EvidenceRecord,
    EvidenceStatus,
    FieldMapping,
    MappingSpecification,
    MappingStatus,
    ProductKnowledgePackage,
    SourceLocation,
    TargetProfile,
)
from mia_dpp.templates import OfficialTemplateRepository


class DeterministicDppPipeline:
    """Compile only accepted UI mappings against pinned official template metadata."""

    def __init__(self, repository: OfficialTemplateRepository) -> None:
        self._repository = repository
        self._compiler = AasCompiler(repository)
        self._validator = AasValidator()

    def build(
        self,
        product_name: str,
        mappings: list[FieldMapping],
        *,
        now: datetime | None = None,
    ) -> DppPackage:
        """Build, verify and report one Digital Nameplate AAS environment."""

        accepted = [
            mapping
            for mapping in mappings
            if mapping.status in {MappingStatus.AUTO, MappingStatus.APPROVED}
        ]
        if not accepted:
            raise MappingError("at least one accepted mapping is required")
        moment = now or datetime.now(UTC)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        moment = moment.astimezone(UTC)

        evidence = tuple(self._evidence(mapping, product_name, moment) for mapping in accepted)
        package = ProductKnowledgePackage(
            product_id=f"product-{hashlib.sha256(product_name.encode()).hexdigest()[:24]}",
            product_name=product_name,
            evidence=evidence,
        )
        template = self._repository.load("digital_nameplate")
        profile = TargetProfile(
            id="idta-digital-nameplate-3-0-1",
            name="IDTA Digital Nameplate 3.0.1",
            template=template.release,
        )
        specification = MappingSpecification(
            id=f"mapping-{hashlib.sha256(self._spec_seed(accepted).encode()).hexdigest()[:24]}",
            target_profile=profile,
            mappings=tuple(
                ApprovedMapping(
                    evidence_id=mapping.evidence_id,
                    target=mapping.target,
                    confidence_assessment=mapping.confidence_assessment,
                )
                for mapping in accepted
            ),
            approved_at=moment,
        )
        artifact = self._compiler.compile(package, specification, template)
        validation = self._validator.validate(artifact, template, specification)
        gaps = gap_report_from_validation(validation)
        shell = artifact.environment["assetAdministrationShells"][0]
        passport_id = str(shell["id"])
        generated_at = moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        return DppPackage(
            product_name=product_name,
            generated_at=generated_at,
            passport_id=passport_id,
            submodel=artifact.submodel,
            environment=artifact.environment,
            artifact_sha256=artifact.sha256,
            target_profile=profile,
            gap_report=gaps,
            validation_report=validation,
            deployable=validation.valid and not gaps.blocks_deployment,
        )

    @staticmethod
    def _evidence(
        mapping: FieldMapping,
        product_name: str,
        acquired_at: datetime,
    ) -> EvidenceRecord:
        source = f"{product_name}\0{mapping.source_field}\0{mapping.source_value}"
        content_hash = hashlib.sha256(source.encode()).hexdigest()
        normalized_field = "_".join(
            part
            for part in "".join(
                character.casefold() if character.isalnum() else " "
                for character in mapping.source_field
            ).split()
            if part
        )
        return EvidenceRecord(
            id=mapping.evidence_id,
            predicate=f"reviewed.{normalized_field or 'field'}",
            value=mapping.source_value,
            source_uri=f"urn:mia:review:{content_hash[:24]}",
            source_content_sha256=content_hash,
            source_location=SourceLocation(excerpt=mapping.source_value[:240]),
            extraction_method="reviewed_mapping",
            extractor_name="mia-workspace",
            extractor_version="2",
            status=(
                EvidenceStatus.VERIFIED
                if mapping.status is MappingStatus.APPROVED
                else EvidenceStatus.OBSERVED
            ),
            acquired_at=acquired_at,
        )

    @staticmethod
    def _spec_seed(mappings: list[FieldMapping]) -> str:
        return "\n".join(
            f"{mapping.evidence_id}:{'/'.join(mapping.target.instance_path)}"
            for mapping in sorted(mappings, key=lambda item: item.target.instance_path)
        )


def build_dpp(
    product_name: str,
    mappings: list[FieldMapping],
    *,
    repository: OfficialTemplateRepository | None = None,
    now: datetime | None = None,
) -> DppPackage:
    """Compatibility entry point used by the FastAPI route and tests."""

    return DeterministicDppPipeline(repository or OfficialTemplateRepository()).build(
        product_name,
        mappings,
        now=now,
    )
