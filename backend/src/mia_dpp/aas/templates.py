"""Normalize pinned official IDTA JSON into MIA-owned contracts."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from mia_dpp.domain.targets import (
    Cardinality,
    ReferenceKey,
    SemanticReference,
    SubmodelTemplate,
    TemplateElement,
    TemplateRelease,
    TemplateSummary,
)

STANDARDS_REPOSITORY_COMMIT = "a9664731a903b29ac5f45e23ab3a25c581f3d92f"
DEFAULT_STANDARDS_ROOT = (
    Path(__file__).resolve().parents[4] / "standards" / "idta-submodel-templates"
)

DIGITAL_NAMEPLATE = TemplateRelease(
    key="digital_nameplate",
    family="Digital nameplate",
    release="3.0.1",
    repository_commit=STANDARDS_REPOSITORY_COMMIT,
    source_path=(
        "published/Digital nameplate/3/0/1/IDTA 02006-3-0-1_Template_Digital Nameplate.json"
    ),
    source_sha256="c2358c18c1d908f943aba76575aec19bb010454d78389ca6bd43f0e5dbae025c",
    metamodel_version="3.0",
)

TECHNICAL_DATA = TemplateRelease(
    key="technical_data",
    family="Technical Data",
    release="2.0.1",
    repository_commit=STANDARDS_REPOSITORY_COMMIT,
    source_path=("published/Technical_Data/2/0/1/IDTA 02003_2-0-1_Template_TechnicalData.json"),
    source_sha256="97aac6192b2657e4a03a2204ecd167494252129b03e58838453e3f1d0abefb6a",
    metamodel_version="3.0",
)

TEMPLATE_RELEASES: Mapping[str, TemplateRelease] = {
    release.key: release for release in (DIGITAL_NAMEPLATE, TECHNICAL_DATA)
}

_ARBITRARY_SEMANTIC_ID = "https://admin-shell.io/SMT/General/Arbitrary"


class TemplateRepositoryError(RuntimeError):
    """Base error for failures at the official-template boundary."""


class StandardsSubmoduleMissingError(TemplateRepositoryError):
    """The pinned standards submodule has not been initialized."""


class UnknownTemplateError(TemplateRepositoryError):
    """A template outside the pinned catalog was requested."""


class TemplateIntegrityError(TemplateRepositoryError):
    """Checked-out standards data differs from the pinned artifact."""


class TemplateElementNotFoundError(TemplateRepositoryError):
    """A normalized path does not occur in a template."""


def _json_pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _semantic_reference(value: object) -> SemanticReference | None:
    if not isinstance(value, Mapping):
        return None
    reference_type = value.get("type")
    raw_keys = value.get("keys")
    if not isinstance(reference_type, str) or not isinstance(raw_keys, list):
        return None
    keys = tuple(
        ReferenceKey(type=raw_key["type"], value=raw_key["value"])
        for raw_key in raw_keys
        if isinstance(raw_key, Mapping)
        and isinstance(raw_key.get("type"), str)
        and isinstance(raw_key.get("value"), str)
        and raw_key["value"]
    )
    if not keys:
        return None
    return SemanticReference(type=reference_type, keys=keys)


def _localized_text(value: object, language: str = "en") -> str | None:
    if not isinstance(value, list):
        return None
    entries = [
        item
        for item in value
        if isinstance(item, Mapping)
        and isinstance(item.get("language"), str)
        and isinstance(item.get("text"), str)
        and item["text"].strip()
    ]
    if not entries:
        return None
    selected = [item["text"].strip() for item in entries if item["language"] == language]
    if not selected:
        first_language = entries[0]["language"]
        selected = [item["text"].strip() for item in entries if item["language"] == first_language]
    return "\n".join(dict.fromkeys(selected))


def _cardinality(value: object, pointer: str) -> Cardinality | None:
    if not isinstance(value, list):
        return None
    raw_values = [
        item.get("value")
        for item in value
        if isinstance(item, Mapping) and item.get("type") == "SMT/Cardinality"
    ]
    if not raw_values:
        return None
    if len(raw_values) != 1:
        raise TemplateIntegrityError(
            f"official template element {pointer} has multiple cardinality qualifiers"
        )
    raw_cardinality = raw_values[0]
    try:
        if not isinstance(raw_cardinality, str):
            raise TypeError
        return Cardinality(raw_cardinality)
    except (TypeError, ValueError) as error:
        raise TemplateIntegrityError(
            f"official template element {pointer} has unsupported cardinality {raw_cardinality!r}"
        ) from error


def _reference_values(reference: SemanticReference | None) -> tuple[str, ...]:
    return () if reference is None else tuple(key.value for key in reference.keys)


def _is_wildcard(reference: SemanticReference | None) -> bool:
    return any(
        value == _ARBITRARY_SEMANTIC_ID
        or value.startswith(f"{_ARBITRARY_SEMANTIC_ID}/")
        or value.startswith(f"{_ARBITRARY_SEMANTIC_ID}Prop")
        or value.startswith(f"{_ARBITRARY_SEMANTIC_ID}MLP")
        or value.startswith(f"{_ARBITRARY_SEMANTIC_ID}File")
        for value in _reference_values(reference)
    )


def _concept_metadata(
    raw_element: Mapping[str, Any],
    concepts: Mapping[str, Mapping[str, Any]],
) -> tuple[str | None, tuple[str, ...], str | None]:
    semantic_id = _semantic_reference(raw_element.get("semanticId"))
    concept = next(
        (concepts[value] for value in _reference_values(semantic_id) if value in concepts),
        None,
    )
    if concept is None:
        return None, (), None
    specifications = concept.get("embeddedDataSpecifications", ())
    if not isinstance(specifications, list):
        return None, (), None
    for specification in specifications:
        if not isinstance(specification, Mapping):
            continue
        content = specification.get("dataSpecificationContent")
        if not isinstance(content, Mapping):
            continue
        unit = content.get("unit") if isinstance(content.get("unit"), str) else None
        definition = _localized_text(content.get("definition"))
        allowed: list[str] = []
        value_list = content.get("valueList")
        if isinstance(value_list, Mapping):
            pairs = value_list.get("valueReferencePairs", ())
            if isinstance(pairs, list):
                allowed.extend(
                    pair["value"]
                    for pair in pairs
                    if isinstance(pair, Mapping) and isinstance(pair.get("value"), str)
                )
        return unit, tuple(dict.fromkeys(allowed)), definition
    return None, (), None


def _child_records(
    raw_element: Mapping[str, Any], pointer: str
) -> Iterable[tuple[Mapping[str, Any], str, bool]]:
    model_type = raw_element.get("modelType")
    for key in ("submodelElements", "value", "statements", "annotations"):
        children = raw_element.get(key)
        if not isinstance(children, list):
            continue
        for index, child in enumerate(children):
            if isinstance(child, Mapping) and isinstance(child.get("modelType"), str):
                yield (
                    child,
                    f"{pointer}/{_json_pointer_token(key)}/{index}",
                    model_type == "SubmodelElementList" and key == "value",
                )
    for key in ("inputVariables", "outputVariables", "inoutputVariables"):
        variables = raw_element.get(key)
        if not isinstance(variables, list):
            continue
        for index, variable in enumerate(variables):
            child = variable.get("value") if isinstance(variable, Mapping) else None
            if isinstance(child, Mapping) and isinstance(child.get("modelType"), str):
                yield child, f"{pointer}/{_json_pointer_token(key)}/{index}/value", False


def _normalize_element(
    raw_element: Mapping[str, Any],
    *,
    pointer: str,
    parent_path: tuple[str, ...],
    list_prototype: bool,
    concepts: Mapping[str, Mapping[str, Any]],
) -> TemplateElement:
    model_type = raw_element.get("modelType")
    if not isinstance(model_type, str) or not model_type:
        raise TemplateIntegrityError(f"official template element {pointer} has no modelType")
    raw_id_short = raw_element.get("idShort")
    id_short = raw_id_short if isinstance(raw_id_short, str) and raw_id_short else None
    if list_prototype:
        segment = "[]"
    elif id_short is not None:
        segment = id_short
    else:
        raise TemplateIntegrityError(
            f"official template element {pointer} has no idShort outside a list prototype"
        )
    path = (*parent_path, segment)
    semantic_id = _semantic_reference(raw_element.get("semanticId"))
    raw_supplemental = raw_element.get("supplementalSemanticIds", ())
    supplemental = (
        tuple(
            reference
            for item in raw_supplemental
            if (reference := _semantic_reference(item)) is not None
        )
        if isinstance(raw_supplemental, list)
        else ()
    )
    unit, allowed_values, concept_description = _concept_metadata(raw_element, concepts)
    children = tuple(
        _normalize_element(
            child,
            pointer=child_pointer,
            parent_path=path,
            list_prototype=is_prototype,
            concepts=concepts,
        )
        for child, child_pointer, is_prototype in _child_records(raw_element, pointer)
    )
    return TemplateElement(
        source_pointer=pointer,
        path=path,
        id_short=id_short,
        model_type=model_type,
        semantic_id=semantic_id,
        supplemental_semantic_ids=supplemental,
        cardinality=_cardinality(raw_element.get("qualifiers"), pointer),
        value_type=(
            raw_element["valueType"] if isinstance(raw_element.get("valueType"), str) else None
        ),
        type_value_list_element=(
            raw_element["typeValueListElement"]
            if isinstance(raw_element.get("typeValueListElement"), str)
            else None
        ),
        value_type_list_element=(
            raw_element["valueTypeListElement"]
            if isinstance(raw_element.get("valueTypeListElement"), str)
            else None
        ),
        semantic_id_list_element=_semantic_reference(raw_element.get("semanticIdListElement")),
        order_relevant=(
            raw_element["orderRelevant"]
            if isinstance(raw_element.get("orderRelevant"), bool)
            else None
        ),
        unit=unit,
        allowed_values=allowed_values,
        wildcard=_is_wildcard(semantic_id),
        description=_localized_text(raw_element.get("description")) or concept_description,
        children=children,
    )


def flatten_elements(template: SubmodelTemplate) -> tuple[TemplateElement, ...]:
    """Return all normalized elements in deterministic pre-order."""

    flattened: list[TemplateElement] = []

    def visit(elements: Iterable[TemplateElement]) -> None:
        for element in elements:
            flattened.append(element)
            visit(element.children)

    visit(template.elements)
    return tuple(flattened)


def summarize_template(template: SubmodelTemplate) -> TemplateSummary:
    """Build the stable summary exposed to API clients."""

    return TemplateSummary(
        key=template.release.key,
        family=template.release.family,
        release=template.release.release,
        id_short=template.id_short,
        template_id=template.template_id,
        semantic_id=template.semantic_id.primary_value,
        source_sha256=template.release.source_sha256,
        element_count=len(flatten_elements(template)),
    )


def resolve_element(template: SubmodelTemplate, path: str | Sequence[str]) -> TemplateElement:
    """Resolve one element by normalized path, including [] list segments."""

    wanted = (
        tuple(part for part in path.split("/") if part) if isinstance(path, str) else tuple(path)
    )
    matches = [element for element in flatten_elements(template) if element.path == wanted]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise TemplateIntegrityError(
            f"template {template.release.key!r} contains duplicate path {'/'.join(wanted)!r}"
        )
    raise TemplateElementNotFoundError(
        f"template {template.release.key!r} has no element at {'/'.join(wanted)!r}"
    )


def resolve_semantic_id(
    template: SubmodelTemplate, semantic_id: str
) -> tuple[TemplateElement, ...]:
    """Resolve elements carrying a primary or supplemental semantic key value."""

    return tuple(
        element
        for element in flatten_elements(template)
        if semantic_id in _reference_values(element.semantic_id)
        or any(
            semantic_id in _reference_values(reference)
            for reference in element.supplemental_semantic_ids
        )
    )


def _read_git_head(root: Path) -> str | None:
    dot_git = root / ".git"
    if dot_git.is_file():
        marker = dot_git.read_text(encoding="utf-8").strip()
        if not marker.startswith("gitdir: "):
            return None
        git_dir = (root / marker.removeprefix("gitdir: ")).resolve()
    elif dot_git.is_dir():
        git_dir = dot_git
    else:
        return None
    head_file = git_dir / "HEAD"
    if not head_file.is_file():
        return None
    head = head_file.read_text(encoding="utf-8").strip()
    if len(head) == 40 and all(character in "0123456789abcdef" for character in head):
        return head
    if not head.startswith("ref: "):
        return None
    reference = head.removeprefix("ref: ")
    loose_reference = git_dir / reference
    if loose_reference.is_file():
        return loose_reference.read_text(encoding="utf-8").strip()
    packed_refs = git_dir / "packed-refs"
    if packed_refs.is_file():
        for line in packed_refs.read_text(encoding="utf-8").splitlines():
            if not line.startswith(("#", "^")) and line.endswith(f" {reference}"):
                return line.split(" ", 1)[0]
    return None


class OfficialTemplateRepository:
    """Read and verify official templates from the pinned IDTA submodule.

    Mapping, coverage, compilation, and validation share this repository so
    authoritative metadata comes from one integrity-checked source.
    """

    def __init__(self, root: Path = DEFAULT_STANDARDS_ROOT) -> None:
        self.root = Path(root)
        self._documents: dict[str, dict[str, Any]] = {}
        self._templates: dict[str, SubmodelTemplate] = {}

    @property
    def repository_commit(self) -> str:
        return STANDARDS_REPOSITORY_COMMIT

    def keys(self) -> tuple[str, ...]:
        return tuple(TEMPLATE_RELEASES)

    def get(self, key: str) -> TemplateRelease:
        try:
            return TEMPLATE_RELEASES[key]
        except KeyError as error:
            available = ", ".join(self.keys())
            raise UnknownTemplateError(
                f"unknown template {key!r}; available templates: {available}"
            ) from error

    def _require_root(self) -> None:
        if not self.root.is_dir():
            raise StandardsSubmoduleMissingError(
                f"official IDTA template submodule is missing at {self.root}. "
                "Run: git submodule update --init standards/idta-submodel-templates"
            )
        actual_commit = _read_git_head(self.root)
        if actual_commit is not None and actual_commit != STANDARDS_REPOSITORY_COMMIT:
            raise TemplateIntegrityError(
                "official IDTA template submodule is checked out at "
                f"{actual_commit}, expected {STANDARDS_REPOSITORY_COMMIT}"
            )

    def _document(self, key: str) -> dict[str, Any]:
        if key in self._documents:
            return self._documents[key]
        release = self.get(key)
        self._require_root()
        source = self.root / release.source_path
        if not source.is_file():
            raise StandardsSubmoduleMissingError(
                f"pinned template file is missing: {source}. "
                "Run: git submodule update --init standards/idta-submodel-templates"
            )
        payload = source.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != release.source_sha256:
            raise TemplateIntegrityError(
                f"template {key!r} has SHA-256 {digest}, expected {release.source_sha256}"
            )
        try:
            document = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TemplateIntegrityError(f"template {key!r} is not valid UTF-8 JSON") from error
        if not isinstance(document, dict):
            raise TemplateIntegrityError(f"template {key!r} does not contain an AAS environment")
        self._documents[key] = document
        return document

    def load_document(self, key: str) -> dict[str, Any]:
        """Return an isolated copy of the authoritative AAS environment JSON."""

        return copy.deepcopy(self._document(key))

    def raw_submodel(self, key: str) -> dict[str, Any]:
        """Return an isolated copy of the authoritative raw submodel."""

        document = self._document(key)
        submodels = document.get("submodels")
        if not isinstance(submodels, list) or len(submodels) != 1:
            raise TemplateIntegrityError(f"template {key!r} must contain exactly one submodel")
        submodel = submodels[0]
        if not isinstance(submodel, dict):
            raise TemplateIntegrityError(f"template {key!r} contains an invalid submodel")
        return copy.deepcopy(submodel)

    def load(self, key: str) -> SubmodelTemplate:
        """Load and normalize one verified template into MIA's domain model."""

        if key in self._templates:
            return self._templates[key]
        release = self.get(key)
        document = self._document(key)
        raw_submodel = self.raw_submodel(key)
        submodel_id = raw_submodel.get("id")
        id_short = raw_submodel.get("idShort")
        semantic_id = _semantic_reference(raw_submodel.get("semanticId"))
        if not isinstance(submodel_id, str) or not submodel_id:
            raise TemplateIntegrityError(f"template {key!r} submodel has no id")
        if not isinstance(id_short, str) or not id_short:
            raise TemplateIntegrityError(f"template {key!r} submodel has no idShort")
        if semantic_id is None:
            raise TemplateIntegrityError(f"template {key!r} submodel has no semanticId")
        raw_concepts = document.get("conceptDescriptions", ())
        concepts = (
            {
                concept["id"]: concept
                for concept in raw_concepts
                if isinstance(concept, Mapping)
                and isinstance(concept.get("id"), str)
                and concept["id"]
            }
            if isinstance(raw_concepts, list)
            else {}
        )
        raw_elements = raw_submodel.get("submodelElements", ())
        if not isinstance(raw_elements, list):
            raise TemplateIntegrityError(f"template {key!r} submodelElements must be a list")
        elements = tuple(
            _normalize_element(
                element,
                pointer=f"/submodels/0/submodelElements/{index}",
                parent_path=(id_short,),
                list_prototype=False,
                concepts=concepts,
            )
            for index, element in enumerate(raw_elements)
            if isinstance(element, Mapping)
        )
        if len(elements) != len(raw_elements):
            raise TemplateIntegrityError(f"template {key!r} contains a non-object element")
        administration = raw_submodel.get("administration")
        administration = administration if isinstance(administration, Mapping) else {}
        template = SubmodelTemplate(
            release=release,
            id=submodel_id,
            id_short=id_short,
            template_id=(
                administration["templateId"]
                if isinstance(administration.get("templateId"), str)
                else None
            ),
            administration_version=(
                administration["version"]
                if isinstance(administration.get("version"), str)
                else None
            ),
            administration_revision=(
                administration["revision"]
                if isinstance(administration.get("revision"), str)
                else None
            ),
            semantic_id=semantic_id,
            elements=elements,
        )
        self._templates[key] = template
        return template

    def summary(self, key: str) -> TemplateSummary:
        return summarize_template(self.load(key))

    def flatten(self, key: str) -> tuple[TemplateElement, ...]:
        return flatten_elements(self.load(key))

    def resolve(self, key: str, path: str | Sequence[str]) -> TemplateElement:
        return resolve_element(self.load(key), path)
