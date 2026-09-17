"""Shared strict Pydantic wire-model behavior."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict


def to_camel(name: str) -> str:
    """Convert Python names to the camelCase expected by the frontend."""

    first, *rest = name.split("_")
    return first + "".join(part.capitalize() for part in rest)


def utc_now() -> datetime:
    """Return an aware UTC time."""

    return datetime.now(UTC)


class WireModel(BaseModel):
    """Strict model with stable camelCase JSON names."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )
