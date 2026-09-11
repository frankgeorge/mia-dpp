"""Boundary for future authoritative semantic concept registries."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from mia_dpp.domain.evidence import EvidenceRecord
from mia_dpp.domain.targets import Requirement


class SemanticConceptRegistry(Protocol):
    """Find authoritative target candidates without coupling resolution to a vendor."""

    async def candidates(
        self,
        evidence: EvidenceRecord,
        requirements: Sequence[Requirement],
    ) -> Sequence[Requirement]: ...
