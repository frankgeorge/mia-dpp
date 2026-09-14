"""Application service composing evidence, reviewed mappings, compilation and validation."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from mia_dpp.aas import AasCompiler, AasValidator, gap_report_from_validation
from mia_dpp.aas.models import DppPackage
from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.domain.evidence import (
    EvidenceRecord,
    EvidenceStatus,
    ProductKnowledgePackage,
    SourceLocation,
)
from mia_dpp.domain.mappings import (
    ApprovedMapping,
    FieldMapping,
    MappingSpecification,
    MappingStatus,
)
from mia_dpp.domain.targets import TargetProfile
from mia_dpp.errors import MappingError


class DeterministicDppPipeline:
    """Turn accepted mappings into a compiled and validated DPP package.

    The API or MIA agent build tool calls this after mapping is complete. It
    selects evidence, invokes ``AasCompiler``, invokes ``AasValidator``, and
    returns the artifact with its deployment gate and gap report.
    """

    def __init__(self, repository: OfficialTemplateRepository) -> None:
        self._repository = repository
        self._compiler = AasCompiler(repository)
        self._validator = AasValidator()

    def build(
        self,
        product_name: str,
        mappings: list[FieldMapping],
        *,
        evidence: tuple[EvidenceRecord, ...] = (),
        now: datetime | None = None,
    ) -> DppPackage:
        """Build and verify one Digital Nameplate AAS from accepted mappings."""

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

        selected_evidence = self._select_evidence(
            accepted,
            evidence,
            product_name=product_name,
            acquired_at=moment,
        )
        package = ProductKnowledgePackage(
            product_id=f"product-{hashlib.sha256(product_name.encode()).hexdigest()[:24]}",
            product_name=product_name,
            evidence=selected_evidence,
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
                    assessment=mapping.assessment,
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
            evidence=selected_evidence,
        )

    @classmethod
    def _select_evidence(
        cls,
        mappings: list[FieldMapping],
        supplied: tuple[EvidenceRecord, ...],
        *,
        product_name: str,
        acquired_at: datetime,
    ) -> tuple[EvidenceRecord, ...]:
        if not supplied:
            return tuple(cls._evidence(mapping, product_name, acquired_at) for mapping in mappings)
        by_id = {item.id: item for item in supplied}
        if len(by_id) != len(supplied):
            raise MappingError("supplied evidence IDs must be unique")
        selected: list[EvidenceRecord] = []
        for mapping in mappings:
            record = by_id.get(mapping.evidence_id)
            if record is None:
                raise MappingError(
                    f"mapping refers to missing supplied evidence {mapping.evidence_id!r}"
                )
            if str(record.value) != mapping.source_value:
                raise MappingError(
                    f"mapping value differs from supplied evidence {mapping.evidence_id!r}"
                )
            selected.append(record)
        return tuple(selected)

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
    evidence: tuple[EvidenceRecord, ...] = (),
    now: datetime | None = None,
) -> DppPackage:
    """Compatibility entry point used by the FastAPI route and tests."""

    return DeterministicDppPipeline(repository or OfficialTemplateRepository()).build(
        product_name,
        mappings,
        evidence=evidence,
        now=now,
    )
