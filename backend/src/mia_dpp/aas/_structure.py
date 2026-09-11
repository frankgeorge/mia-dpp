"""Small shared helpers for traversing serialized AAS structure."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _reference_value(raw: object) -> str | None:
    if not isinstance(raw, Mapping):
        return None
    keys = raw.get("keys")
    if not isinstance(keys, list) or not keys or not isinstance(keys[0], Mapping):
        return None
    value = keys[0].get("value")
    return value if isinstance(value, str) else None


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
