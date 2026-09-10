"""Canonical JSON and content identity helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Serialize JSON data identically across calls and machines."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_json(value: Any) -> str:
    """Hash a value after canonical JSON serialization."""

    return hashlib.sha256(canonical_json(value).encode()).hexdigest()
