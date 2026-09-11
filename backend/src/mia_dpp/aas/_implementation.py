"""Shared implementation for deterministic AAS compilation and validation."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from importlib.metadata import version
from typing import Any, cast

from aas_core3 import jsonization, verification

from mia_dpp.canonical import sha256_json
from mia_dpp.errors import CompilationError, MappingError
from mia_dpp.models import (
    AasArtifact,
    ApprovedMapping,
    Cardinality,
    Gap,
    GapReport,
    MappingSpecification,
    MappingTarget,
    ProductKnowledgePackage,
    SemanticReference,
    Severity,
    SubmodelTemplate,
    TemplateElement,
    ValidationCategory,
    ValidationFinding,
    ValidationReport,
)
from mia_dpp.templates import OfficialTemplateRepository, resolve_element

_VALUE_MODEL_TYPES = {"Property", "MultiLanguageProperty", "Range", "File", "Blob"}
_CONTAINER_MODEL_TYPES = {"SubmodelElementCollection", "SubmodelElementList", "Entity"}
_ID_SHORT_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _reference_json(reference: SemanticReference) -> dict[str, Any]:
    return reference.model_dump(mode="json", by_alias=True)


def _reference_value(raw: object) -> str | None:
    if not isinstance(raw, Mapping):
        return None
    keys = raw.get("keys")
    if not isinstance(keys, list) or not keys or not isinstance(keys[0], Mapping):
        return None
    value = keys[0].get("value")
    return value if isinstance(value, str) else None


def _id_short(value: str, fallback: str = "Product") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", value.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"{fallback}_{cleaned}" if cleaned else fallback
    return cleaned[:128]


def _children(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    model_type = raw.get("modelType")
    if not isinstance(model_type, str):
        return []
    key = {
        "Submodel": "submodelElements",
        "SubmodelElementCollection": "value",
        "SubmodelElementList": "value",
        "Entity": "statements",
        "AnnotatedRelationshipElement": "annotations",
    }.get(model_type)
    value = raw.get(key) if key else None
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _child_key(model_type: str) -> str | None:
    return {
        "Submodel": "submodelElements",
        "SubmodelElementCollection": "value",
        "SubmodelElementList": "value",
        "Entity": "statements",
        "AnnotatedRelationshipElement": "annotations",
    }.get(model_type)


def _template_segment(raw: Mapping[str, Any], parent_model_type: str) -> str:
    if parent_model_type == "SubmodelElementList":
        return "[]"
    value = raw.get("idShort")
    if not isinstance(value, str) or not value:
        raise CompilationError("official template element has no usable idShort")
    return value


def _metadata(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Copy instance-relevant template metadata, excluding examples and qualifiers."""

    result: dict[str, Any] = {}
    for key in (
        "category",
        "idShort",
        "semanticId",
        "supplementalSemanticIds",
        "modelType",
        "valueType",
        "contentType",
        "orderRelevant",
        "typeValueListElement",
        "valueTypeListElement",
        "semanticIdListElement",
    ):
        if key in raw:
            result[key] = copy.deepcopy(raw[key])
    if result.get("idShort") == "":
        result.pop("idShort", None)
    return result


def _set_leaf_value(raw: dict[str, Any], mapping: ApprovedMapping, value: str) -> None:
    target = mapping.target
    raw["idShort"] = target.id_short
    raw["semanticId"] = _reference_json(target.semantic_id)
    raw["modelType"] = target.model_type
    if target.value_type is not None:
        raw["valueType"] = target.value_type
    model_type = target.model_type
    if model_type == "Property":
        raw["value"] = value
    elif model_type == "MultiLanguageProperty":
        raw["value"] = [{"language": "en", "text": value}]
    elif model_type == "Range":
        parts = re.split(r"\s*(?:-|\u2013|to|bis)\s*", value, maxsplit=1)
        if len(parts) != 2:
            raise CompilationError(f"range value {value!r} has no deterministic bounds")
        raw["min"], raw["max"] = parts
    elif model_type == "File":
        raw["value"] = value
    elif model_type == "Blob":
        raw["value"] = value
    else:
        raise CompilationError(f"unsupported mapped model type: {model_type}")


class AasCompiler:
    """Project approved evidence onto official template nodes and serialize with aas-core."""

    def __init__(self, repository: OfficialTemplateRepository) -> None:
        self._repository = repository

    def compile(
        self,
        package: ProductKnowledgePackage,
        specification: MappingSpecification,
        template: SubmodelTemplate,
    ) -> AasArtifact:
        """Build one stable AAS environment from an approved mapping specification."""

        if specification.target_profile.template != template.release:
            raise MappingError("mapping specification does not select the loaded template")
        evidence = {item.id: item for item in package.evidence}
        resolved: list[tuple[ApprovedMapping, str]] = []
        for approved in specification.mappings:
            if approved.evidence_id not in evidence:
                raise MappingError(f"mapping references unknown evidence {approved.evidence_id!r}")
            value = evidence[approved.evidence_id].value
            if not isinstance(value, (str, int, float, bool)):
                raise CompilationError("AAS scalar targets require scalar evidence values")
            self._validate_target(approved.target, template)
            resolved.append((approved, str(value)))

        stable_seed = {
            "productId": package.product_id,
            "productName": package.product_name,
            "template": template.release.model_dump(mode="json"),
            "mappings": [
                {
                    "evidence": approved.evidence_id,
                    "path": approved.target.instance_path,
                    "value": value,
                }
                for approved, value in sorted(
                    resolved, key=lambda item: item[0].target.instance_path
                )
            ],
        }
        suffix = sha256_json(stable_seed)[:32]
        aas_id = f"urn:mia:aas:{suffix}"
        asset_id = f"urn:mia:asset:{suffix}"
        submodel_id = f"urn:mia:submodel:{template.release.key}:{suffix}"

        raw_submodel = self._repository.raw_submodel(template.release.key)
        raw_elements = raw_submodel.get("submodelElements")
        if not isinstance(raw_elements, list):
            raise CompilationError("official template submodelElements is not a list")
        mappings = sorted(
            (approved for approved, _ in resolved),
            key=lambda item: item.target.instance_path,
        )
        values = {approved.evidence_id: value for approved, value in resolved}
        projected = self._project_children(
            raw_elements,
            parent_path=(template.id_short,),
            parent_model_type="Submodel",
            mappings=mappings,
            values=values,
        )
        projected = self._add_system_elements(projected, raw_elements, template, asset_id)

        submodel: dict[str, Any] = {
            "id": submodel_id,
            "idShort": template.id_short,
            "kind": "Instance",
            "semanticId": _reference_json(template.semantic_id),
            "submodelElements": projected,
            "modelType": "Submodel",
        }
        shell: dict[str, Any] = {
            "id": aas_id,
            "idShort": _id_short(package.product_name),
            "assetInformation": {
                "assetKind": "Instance",
                "globalAssetId": asset_id,
            },
            "submodels": [
                {
                    "type": "ModelReference",
                    "keys": [{"type": "Submodel", "value": submodel_id}],
                }
            ],
            "modelType": "AssetAdministrationShell",
        }
        document = {
            "assetAdministrationShells": [shell],
            "submodels": [submodel],
        }
        try:
            environment = jsonization.environment_from_jsonable(document)
            canonical = cast(dict[str, Any], jsonization.to_jsonable(environment))
        except (TypeError, ValueError) as error:
            raise CompilationError(f"aas-core rejected compiled environment: {error}") from error
        canonical_submodel = cast(dict[str, Any], canonical["submodels"][0])
        return AasArtifact(
            environment=canonical,
            submodel=canonical_submodel,
            sha256=sha256_json(canonical),
            compiler_name="mia-official-template-projector+aas-core3.0",
            compiler_version=version("aas-core3.0"),
        )

    @staticmethod
    def _validate_target(target: MappingTarget, template: SubmodelTemplate) -> None:
        if target.template_key != template.release.key:
            raise MappingError("mapping target belongs to another template")
        if target.template_release != template.release.release:
            raise MappingError("mapping target belongs to another template release")
        official = resolve_element(template, target.template_path)
        if official.model_type not in _VALUE_MODEL_TYPES:
            raise MappingError("mapping target is not a value-bearing template element")
        if target.model_type != official.model_type:
            raise MappingError("mapping target model type differs from official template")
        if target.value_type != official.value_type:
            raise MappingError("mapping target value type differs from official template")
        if target.wildcard != official.wildcard:
            raise MappingError("mapping target wildcard policy differs from official template")
        if not official.wildcard:
            if official.semantic_id is None or target.semantic_id != official.semantic_id:
                raise MappingError("mapping target semantic ID differs from official template")
            if target.instance_path != target.template_path:
                raise MappingError("fixed template target path cannot be changed")
            if target.id_short != official.id_short:
                raise MappingError("fixed template target idShort cannot be changed")
        else:
            if not _ID_SHORT_PATTERN.fullmatch(target.id_short):
                raise MappingError("wildcard target idShort is invalid")
            if target.instance_path[:-1] != target.template_path[:-1]:
                raise MappingError("wildcard target parent path cannot be changed")
            if target.instance_path[-1] != target.id_short:
                raise MappingError("wildcard instance path must end with its idShort")

    def _project_children(
        self,
        raw_children: Sequence[object],
        *,
        parent_path: tuple[str, ...],
        parent_model_type: str,
        mappings: Sequence[ApprovedMapping],
        values: Mapping[str, str],
    ) -> list[dict[str, Any]]:
        projected: list[dict[str, Any]] = []
        for raw_value in raw_children:
            if not isinstance(raw_value, Mapping):
                continue
            raw = cast(Mapping[str, Any], raw_value)
            segment = _template_segment(raw, parent_model_type)
            path = (*parent_path, segment)
            relevant = [
                mapping for mapping in mappings if mapping.target.template_path[: len(path)] == path
            ]
            if not relevant:
                continue
            exact = [mapping for mapping in relevant if mapping.target.template_path == path]
            model_type = raw.get("modelType")
            if not isinstance(model_type, str):
                continue
            if exact:
                for mapping in exact:
                    instance = _metadata(raw)
                    _set_leaf_value(instance, mapping, values[mapping.evidence_id])
                    if parent_model_type == "SubmodelElementList":
                        instance.pop("idShort", None)
                    projected.append(instance)
                continue
            key = _child_key(model_type)
            if key is None or model_type not in _CONTAINER_MODEL_TYPES:
                raise CompilationError(
                    f"target path {'/'.join(path)!r} crosses unsupported {model_type}"
                )
            descendants = self._project_children(
                _children(raw),
                parent_path=path,
                parent_model_type=model_type,
                mappings=relevant,
                values=values,
            )
            if descendants:
                instance = _metadata(raw)
                instance[key] = descendants
                if parent_model_type == "SubmodelElementList":
                    instance.pop("idShort", None)
                projected.append(instance)
        return projected

    @staticmethod
    def _add_system_elements(
        projected: list[dict[str, Any]],
        raw_elements: Sequence[object],
        template: SubmodelTemplate,
        asset_id: str,
    ) -> list[dict[str, Any]]:
        """Populate structural/identifier requirements without inventing product facts."""

        present = {item.get("idShort") for item in projected}
        additions: list[dict[str, Any]] = []
        for raw_value in raw_elements:
            if not isinstance(raw_value, Mapping):
                continue
            id_short = raw_value.get("idShort")
            if id_short in present:
                continue
            if template.release.key == "digital_nameplate" and id_short == "URIOfTheProduct":
                instance = _metadata(cast(Mapping[str, Any], raw_value))
                instance["value"] = asset_id
                additions.append(instance)
            elif template.release.key == "digital_nameplate" and id_short == "AddressInformation":
                # The Nameplate JSON declares this required drop-in but does not embed
                # its children. Keep the required structural node and report limited
                # deep validation as a warning.
                instance = _metadata(cast(Mapping[str, Any], raw_value))
                additions.append(instance)
        result = [*projected, *additions]
        order = {
            item.get("idShort"): index
            for index, item in enumerate(raw_elements)
            if isinstance(item, Mapping)
        }
        return sorted(result, key=lambda item: order.get(item.get("idShort"), len(order)))


class AasValidator:
    """Combine strict aas-core checks with template-path conformance checks."""

    def validate(
        self,
        artifact: AasArtifact,
        template: SubmodelTemplate,
        specification: MappingSpecification,
    ) -> ValidationReport:
        findings: list[ValidationFinding] = []
        if sha256_json(artifact.environment) != artifact.sha256:
            findings.append(
                ValidationFinding(
                    category=ValidationCategory.POLICY,
                    code="MIA-DIGEST-001",
                    message="Artifact content differs from its recorded digest.",
                    severity=Severity.ERROR,
                )
            )
        try:
            environment = jsonization.environment_from_jsonable(artifact.environment)
            findings.extend(
                ValidationFinding(
                    category=ValidationCategory.METAMODEL,
                    code="AAS-METAMODEL",
                    message=str(error.cause),
                    severity=Severity.ERROR,
                    instance_path=(str(error.path),),
                )
                for error in verification.verify(environment)
            )
        except (TypeError, ValueError) as error:
            findings.append(
                ValidationFinding(
                    category=ValidationCategory.METAMODEL,
                    code="AAS-DESERIALIZATION",
                    message=str(error),
                    severity=Severity.ERROR,
                )
            )

        submodel = artifact.submodel
        if _reference_value(submodel.get("semanticId")) != template.semantic_id.primary_value:
            findings.append(
                ValidationFinding(
                    category=ValidationCategory.TEMPLATE,
                    code="IDTA-SUBMODEL-SEMANTIC-ID",
                    message="Submodel semantic ID differs from the selected official template.",
                    severity=Severity.ERROR,
                    expected=template.semantic_id.primary_value,
                    actual=_reference_value(submodel.get("semanticId")),
                )
            )
        actual_elements = submodel.get("submodelElements")
        actual_elements = actual_elements if isinstance(actual_elements, list) else []
        findings.extend(
            self._validate_children(
                template.elements,
                actual_elements,
                parent_present=True,
            )
        )
        for approved in specification.mappings:
            findings.extend(self._validate_mapped_target(approved.target, actual_elements))
        if template.release.key == "digital_nameplate":
            findings.append(
                ValidationFinding(
                    category=ValidationCategory.TEMPLATE,
                    code="IDTA-EXTERNAL-DROPIN",
                    message=(
                        "AddressInformation is an external Contact Information drop-in; "
                        "the pinned Nameplate JSON does not contain its child definition."
                    ),
                    severity=Severity.WARNING,
                    instance_path=(template.id_short, "AddressInformation"),
                    template_path=(template.id_short, "AddressInformation"),
                )
            )
        return ValidationReport(
            valid=not any(item.severity is Severity.ERROR for item in findings),
            template_key=template.release.key,
            template_release=template.release.release,
            artifact_sha256=artifact.sha256,
            validator_versions={
                "aas-core3.0": version("aas-core3.0"),
                "mia-template-validator": "1",
            },
            findings=tuple(findings),
        )

    def _validate_children(
        self,
        expected: Sequence[TemplateElement],
        actual: Sequence[object],
        *,
        parent_present: bool,
    ) -> list[ValidationFinding]:
        if not parent_present:
            return []
        findings: list[ValidationFinding] = []
        actual_dicts = [item for item in actual if isinstance(item, Mapping)]
        for element in expected:
            if element.path[-1] == "[]":
                matches = actual_dicts
            elif element.wildcard:
                matches = [
                    item for item in actual_dicts if item.get("modelType") == element.model_type
                ]
            else:
                matches = [item for item in actual_dicts if item.get("idShort") == element.id_short]
            cardinality = element.cardinality or Cardinality.ZERO_TO_MANY
            if len(matches) < cardinality.minimum:
                findings.append(
                    ValidationFinding(
                        category=ValidationCategory.TEMPLATE,
                        code="IDTA-CARDINALITY-MIN",
                        message=f"Required template element {'/'.join(element.path)} is missing.",
                        severity=Severity.ERROR,
                        template_path=element.path,
                        expected=cardinality.value,
                        actual=str(len(matches)),
                    )
                )
                continue
            if cardinality.maximum is not None and len(matches) > cardinality.maximum:
                findings.append(
                    ValidationFinding(
                        category=ValidationCategory.TEMPLATE,
                        code="IDTA-CARDINALITY-MAX",
                        message=f"Template element {'/'.join(element.path)} occurs too often.",
                        severity=Severity.ERROR,
                        template_path=element.path,
                        expected=cardinality.value,
                        actual=str(len(matches)),
                    )
                )
            for match in matches:
                findings.extend(self._validate_element_shape(element, match))
                child_values = _children(cast(Mapping[str, Any], match))
                findings.extend(
                    self._validate_children(
                        element.children,
                        child_values,
                        parent_present=True,
                    )
                )
        return findings

    @staticmethod
    def _validate_element_shape(
        expected: TemplateElement, actual: Mapping[str, Any]
    ) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        actual_type = actual.get("modelType")
        if actual_type != expected.model_type:
            findings.append(
                ValidationFinding(
                    category=ValidationCategory.TEMPLATE,
                    code="IDTA-MODEL-TYPE",
                    message="Instance model type differs from the template.",
                    severity=Severity.ERROR,
                    instance_path=expected.path,
                    template_path=expected.path,
                    expected=expected.model_type,
                    actual=str(actual_type),
                )
            )
        actual_value_type = actual.get("valueType")
        if expected.value_type is not None and actual_value_type != expected.value_type:
            findings.append(
                ValidationFinding(
                    category=ValidationCategory.TEMPLATE,
                    code="IDTA-VALUE-TYPE",
                    message="Instance value type differs from the template.",
                    severity=Severity.ERROR,
                    instance_path=expected.path,
                    template_path=expected.path,
                    expected=expected.value_type,
                    actual=str(actual_value_type),
                )
            )
        if not expected.wildcard and expected.semantic_id is not None:
            actual_semantic_id = _reference_value(actual.get("semanticId"))
            expected_values = {key.value for key in expected.semantic_id.keys} | {
                key.value
                for reference in expected.supplemental_semantic_ids
                for key in reference.keys
            }
            if actual_semantic_id not in expected_values:
                findings.append(
                    ValidationFinding(
                        category=ValidationCategory.TEMPLATE,
                        code="IDTA-SEMANTIC-ID",
                        message="Instance semantic ID differs from the template.",
                        severity=Severity.ERROR,
                        instance_path=expected.path,
                        template_path=expected.path,
                        expected=" or ".join(sorted(expected_values)),
                        actual=actual_semantic_id,
                    )
                )
        return findings

    @staticmethod
    def _validate_mapped_target(
        target: MappingTarget, root: Sequence[object]
    ) -> list[ValidationFinding]:
        current: Sequence[Mapping[str, Any]] = [item for item in root if isinstance(item, Mapping)]
        for index, segment in enumerate(target.instance_path[1:]):
            if segment == "[]":
                matches = current
            else:
                matches = [item for item in current if item.get("idShort") == segment]
            if not matches:
                return [
                    ValidationFinding(
                        category=ValidationCategory.TEMPLATE,
                        code="MIA-MAPPED-TARGET-MISSING",
                        message="An approved mapping is absent from the compiled artifact.",
                        severity=Severity.ERROR,
                        instance_path=target.instance_path,
                        template_path=target.template_path,
                    )
                ]
            if index < len(target.instance_path[1:]) - 1:
                current = _children(matches[0])
        return []


def gap_report_from_validation(report: ValidationReport) -> GapReport:
    """Present missing required template elements separately from all validation detail."""

    gaps = tuple(
        Gap(
            template_path=finding.template_path,
            message=finding.message,
            severity=finding.severity,
        )
        for finding in report.findings
        if finding.code == "IDTA-CARDINALITY-MIN"
    )
    return GapReport(
        template_key=report.template_key,
        gaps=gaps,
        blocks_deployment=any(gap.severity is Severity.ERROR for gap in gaps),
    )
