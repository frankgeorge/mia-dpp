"""Typed artifact metadata and lineage contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import AwareDatetime

from mia_dpp.domain.base import WireModel


class ArtifactKind(StrEnum):
    SEARCH = "search"
    SOURCE = "source"
    RAW = "raw"
    EVIDENCE = "evidence"
    MAPPING = "mapping"
    COVERAGE = "coverage"
    REVIEW = "review"
    AAS = "aas"
    VALIDATION = "validation"
    TRACE = "trace"
    EXPORT = "export"


class WorkspaceArtifact(WireModel):
    """Manifest entry for one inspectable file owned by a thread."""

    id: str
    kind: ArtifactKind
    name: str
    relative_path: str
    created_at: AwareDatetime
    created_by: str
    content_type: str
    sha256: str
    size: int
    product_id: str | None = None
    source_url: str | None = None
    derived_from: tuple[str, ...] = ()
    downloadable: bool = True


class WorkspaceManifest(WireModel):
    """Small registry of a thread's artifacts; file contents stay separate."""

    thread_id: str
    created_at: datetime
    updated_at: datetime
    artifacts: tuple[WorkspaceArtifact, ...] = ()
