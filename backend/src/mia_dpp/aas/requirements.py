"""Derive stable, actionable requirements from normalized official templates."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from mia_dpp.models import (
    Cardinality,
    Requirement,
    RequirementInventory,
    RequirementKind,
    SubmodelTemplate,
    TemplateElement,
)

_VALUE_MODEL_TYPES = frozenset(
    {
        "Property",
        "MultiLanguageProperty",
        "Range",
        "File",
        "Blob",
        "ReferenceElement",
        "RelationshipElement",
        "AnnotatedRelationshipElement",
    }
)


def build_requirement_inventory(
    templates: Sequence[SubmodelTemplate],
) -> RequirementInventory:
    """Build requirements for any selected normalized template collection.

    Containers with normalized children provide hierarchy rather than pretending
    to need scalar evidence. Opaque leaf structures remain visible requirements.
    """

    if not templates:
        raise ValueError("at least one template is required")
    template_keys = [template.release.key for template in templates]
    if len(template_keys) != len(set(template_keys)):
        raise ValueError("selected template keys must be unique")

    requirements: list[Requirement] = []
    for template in templates:
        for element in template.elements:
            _collect_requirements(
                template,
                element,
                parent_is_unconditionally_present=True,
                output=requirements,
            )
    return RequirementInventory(
        selected_templates=tuple(template.release for template in templates),
        requirements=tuple(requirements),
    )


def _collect_requirements(
    template: SubmodelTemplate,
    element: TemplateElement,
    *,
    parent_is_unconditionally_present: bool,
    output: list[Requirement],
) -> None:
    locally_required = element.cardinality in {
        Cardinality.ONE,
        Cardinality.ONE_TO_MANY,
    }
    globally_required = parent_is_unconditionally_present and locally_required
    conditional = locally_required and not parent_is_unconditionally_present

    kind = (
        RequirementKind.VALUE
        if element.model_type in _VALUE_MODEL_TYPES
        else RequirementKind.STRUCTURAL
    )
    if kind is RequirementKind.VALUE or not element.children:
        output.append(
            Requirement(
                id=_requirement_id(
                    template.release.key,
                    template.release.release,
                    element.path,
                ),
                template_key=template.release.key,
                template_release=template.release.release,
                template_path=element.path,
                id_short=element.id_short,
                semantic_id=element.semantic_id,
                supplemental_semantic_ids=element.supplemental_semantic_ids,
                model_type=element.model_type,
                value_type=element.value_type,
                cardinality=element.cardinality,
                kind=kind,
                required=globally_required,
                conditional=conditional,
                unit=element.unit,
                allowed_values=element.allowed_values,
                description=element.description,
                wildcard=element.wildcard,
            )
        )

    descendants_are_unconditionally_present = globally_required
    for child in element.children:
        _collect_requirements(
            template,
            child,
            parent_is_unconditionally_present=descendants_are_unconditionally_present,
            output=output,
        )


def _requirement_id(template_key: str, release: str, path: tuple[str, ...]) -> str:
    identity = "\0".join((template_key, release, *path))
    return f"req-{hashlib.sha256(identity.encode()).hexdigest()[:24]}"
