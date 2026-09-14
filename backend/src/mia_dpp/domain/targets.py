"""Official template metadata and target requirements."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from mia_dpp.domain.base import WireModel


class RequirementKind(StrEnum):
    VALUE = "value"
    STRUCTURAL = "structural"


class Cardinality(StrEnum):
    ONE = "One"
    ZERO_TO_ONE = "ZeroToOne"
    ONE_TO_MANY = "OneToMany"
    ZERO_TO_MANY = "ZeroToMany"

    @property
    def minimum(self) -> int:
        return 1 if self in {Cardinality.ONE, Cardinality.ONE_TO_MANY} else 0

    @property
    def maximum(self) -> int | None:
        return 1 if self in {Cardinality.ONE, Cardinality.ZERO_TO_ONE} else None


class ReferenceKey(WireModel):
    type: str = Field(min_length=1)
    value: str = Field(min_length=1)


class SemanticReference(WireModel):
    type: str = Field(min_length=1)
    keys: tuple[ReferenceKey, ...] = Field(min_length=1)

    @property
    def primary_value(self) -> str:
        return self.keys[0].value


class TemplateRelease(WireModel):
    """Exact official template artifact selected for a build."""

    key: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    family: str = Field(min_length=1)
    release: str = Field(pattern=r"^\d+[.]\d+[.]\d+$")
    repository_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_path: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metamodel_version: str = Field(min_length=1)


class TemplateElement(WireModel):
    """Normalized recursive view of an official submodel template element."""

    source_pointer: str = Field(min_length=1)
    path: tuple[str, ...] = Field(min_length=1)
    id_short: str | None = None
    model_type: str = Field(min_length=1)
    semantic_id: SemanticReference | None = None
    supplemental_semantic_ids: tuple[SemanticReference, ...] = ()
    cardinality: Cardinality | None = None
    value_type: str | None = None
    type_value_list_element: str | None = None
    value_type_list_element: str | None = None
    semantic_id_list_element: SemanticReference | None = None
    order_relevant: bool | None = None
    unit: str | None = None
    allowed_values: tuple[str, ...] = ()
    wildcard: bool = False
    description: str | None = None
    children: tuple[TemplateElement, ...] = ()


class SubmodelTemplate(WireModel):
    release: TemplateRelease
    id: str = Field(min_length=1)
    id_short: str = Field(min_length=1)
    template_id: str | None = None
    administration_version: str | None = None
    administration_revision: str | None = None
    semantic_id: SemanticReference
    elements: tuple[TemplateElement, ...]


class Requirement(WireModel):
    """One actionable expectation derived from an official template element."""

    id: str = Field(pattern=r"^req-[0-9a-f]{24}$")
    template_key: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    template_release: str = Field(pattern=r"^\d+[.]\d+[.]\d+$")
    template_path: tuple[str, ...] = Field(min_length=1)
    id_short: str | None = None
    semantic_id: SemanticReference | None = None
    supplemental_semantic_ids: tuple[SemanticReference, ...] = ()
    model_type: str = Field(min_length=1)
    value_type: str | None = None
    cardinality: Cardinality | None = None
    kind: RequirementKind
    required: bool
    conditional: bool
    unit: str | None = None
    allowed_values: tuple[str, ...] = ()
    description: str | None = None
    wildcard: bool = False

    @model_validator(mode="after")
    def obligation_is_unambiguous(self) -> Requirement:
        if self.required and self.conditional:
            raise ValueError("a requirement cannot be both globally required and conditional")
        return self


class TemplateIndex(WireModel):
    """The single application-level index of official template targets.

    Template loading builds this once. Mapping, coverage, completion, and AAS
    projection consume the same normalized requirements instead of interpreting
    official IDTA files independently.
    """

    selected_templates: tuple[TemplateRelease, ...] = Field(min_length=1)
    requirements: tuple[Requirement, ...]

    @model_validator(mode="after")
    def identities_are_unique_and_selected(self) -> TemplateIndex:
        template_keys = [item.key for item in self.selected_templates]
        if len(template_keys) != len(set(template_keys)):
            raise ValueError("selected template keys must be unique")
        requirement_ids = [item.id for item in self.requirements]
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError("requirement IDs must be unique")
        releases = {(item.key, item.release) for item in self.selected_templates}
        if any(
            (item.template_key, item.template_release) not in releases for item in self.requirements
        ):
            raise ValueError("every requirement must belong to a selected template release")
        return self


class TargetProfile(WireModel):
    """Versioned choice of one official target for deterministic compilation."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    template: TemplateRelease
    aas_metamodel_version: Literal["3.0"] = "3.0"
    language: str = "en"


class TemplateSummary(WireModel):
    key: str
    family: str
    release: str
    id_short: str
    template_id: str | None
    semantic_id: str
    source_sha256: str
    element_count: int
