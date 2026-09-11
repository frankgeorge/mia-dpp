"""Compatibility imports for MIA's provider-neutral reasoning service."""

import json

import httpx

from mia_dpp.integrations.openrouter import OpenRouterReasoningService
from mia_dpp.llm.reasoning import (
    ReasoningService,
    UnconfiguredReasoningService,
)

__all__ = [
    "OpenRouterReasoningService",
    "ReasoningService",
    "UnconfiguredReasoningService",
    "httpx",
    "json",
]
