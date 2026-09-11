"""Stable, lazily configured FastAPI application boundary."""

from __future__ import annotations

from typing import Any

_ROUTE_EXPORTS = {
    "app",
    "settings",
    "templates",
    "website_ingestion",
    "reasoning",
    "agent_workflow",
}


def __getattr__(name: str) -> Any:
    if name not in _ROUTE_EXPORTS:
        raise AttributeError(name)
    from mia_dpp.api import routes

    return getattr(routes, name)
