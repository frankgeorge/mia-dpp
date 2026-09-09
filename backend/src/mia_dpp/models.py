"""Python equivalents of the data structures currently used by the frontend."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def to_camel(name: str) -> str:
    """Convert Python field names to the camelCase expected by the frontend."""

    first, *rest = name.split("_")
    return first + "".join(part.capitalize() for part in rest)


class WireModel(BaseModel):
    """Validate API data while retaining the frontend's existing JSON names."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )


class MappingStatus(StrEnum):
    AUTO = "auto"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"


class MappingDraft(WireModel):
    """A source field proposed for one Digital Nameplate element."""

    source_field: str
    source_value: str
    target_element: str
    semantic_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    from_graph: bool = False


class FieldMapping(MappingDraft):
    """A proposed mapping after the frontend assigns an ID and review state."""

    id: str
    status: MappingStatus


class ProposedFieldMapping(MappingDraft):
    """A backend proposal with the current confidence-based review state."""

    status: MappingStatus


class GraphEntry(WireModel):
    source_field: str
    target_element: str
    semantic_id: str
    verified_at: str
    corrections: int


class DppPackage(WireModel):
    product_name: str
    generated_at: str
    submodel: dict[str, Any]
    passport_id: str


class DemoProposal(WireModel):
    product_name: str
    mappings: tuple[MappingDraft, ...]


class MappingProposal(WireModel):
    product_name: str
    mappings: tuple[ProposedFieldMapping, ...]


class ChatMessage(WireModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(WireModel):
    messages: tuple[ChatMessage, ...] = ()
    graph: tuple[GraphEntry, ...] = ()


class ChatResponse(WireModel):
    reply: str
    proposal: MappingProposal | None = None
    generate: bool = False
    mode: str
    nameplate_elements: tuple[dict[str, Any], ...]


class DppBuildRequest(WireModel):
    product_name: str
    mappings: tuple[FieldMapping, ...]
