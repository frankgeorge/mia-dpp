"""Filesystem workspace with manifest-based access and lineage."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

from mia_dpp.workspace.models import ArtifactKind, WorkspaceArtifact, WorkspaceManifest

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")


class WorkspaceStore(Protocol):
    """Boundary for registering, reading, listing, and exporting thread artifacts."""

    def write_json(
        self,
        thread_id: str,
        kind: ArtifactKind,
        name: str,
        value: Any,
        **metadata: Any,
    ) -> WorkspaceArtifact: ...

    def write_bytes(
        self,
        thread_id: str,
        kind: ArtifactKind,
        name: str,
        data: bytes,
        *,
        content_type: str,
        **metadata: Any,
    ) -> WorkspaceArtifact: ...

    def list_artifacts(self, thread_id: str) -> tuple[WorkspaceArtifact, ...]: ...

    def read_artifact(
        self, thread_id: str, artifact_id: str
    ) -> tuple[WorkspaceArtifact, bytes]: ...

    def export_zip(self, thread_id: str) -> bytes: ...

    def combined_export(self, thread_id: str) -> dict[str, Any]: ...


class FileWorkspaceStore:
    """Local workspace implementation whose manifest is the only file registry.

    API callers use opaque artifact IDs, never filesystem paths. Thread and
    artifact identifiers are validated before any path is resolved.
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def write_json(
        self,
        thread_id: str,
        kind: ArtifactKind,
        name: str,
        value: Any,
        **metadata: Any,
    ) -> WorkspaceArtifact:
        data = json.dumps(value, ensure_ascii=False, indent=2, default=str).encode()
        return self.write_bytes(
            thread_id,
            kind,
            name,
            data,
            content_type="application/json",
            **metadata,
        )

    def write_bytes(
        self,
        thread_id: str,
        kind: ArtifactKind,
        name: str,
        data: bytes,
        *,
        content_type: str,
        **metadata: Any,
    ) -> WorkspaceArtifact:
        directory = self._thread_dir(thread_id)
        category = directory / kind.value
        category.mkdir(parents=True, exist_ok=True)
        safe_name = self._safe_name(name)
        artifact_id = "artifact-" + uuid.uuid4().hex
        relative = f"{kind.value}/{artifact_id}-{safe_name}"
        path = directory / relative
        path.write_bytes(data)
        now = datetime.now(UTC)
        artifact = WorkspaceArtifact(
            id=artifact_id,
            kind=kind,
            name=name,
            relative_path=relative,
            created_at=now,
            created_by=str(metadata.get("created_by", "mia")),
            product_id=metadata.get("product_id"),
            source_url=metadata.get("source_url"),
            derived_from=tuple(metadata.get("derived_from", ())),
            content_type=content_type,
            sha256=hashlib.sha256(data).hexdigest(),
            size=len(data),
        )
        manifest = self._manifest(thread_id)
        self._save_manifest(
            directory,
            manifest.model_copy(
                update={"updated_at": now, "artifacts": (*manifest.artifacts, artifact)}
            ),
        )
        return artifact

    def list_artifacts(self, thread_id: str) -> tuple[WorkspaceArtifact, ...]:
        return self._manifest(thread_id).artifacts

    def read_artifact(self, thread_id: str, artifact_id: str) -> tuple[WorkspaceArtifact, bytes]:
        if not _SAFE_ID.fullmatch(artifact_id):
            raise ValueError("invalid artifact ID")
        directory = self._thread_dir(thread_id)
        artifact = next(
            (item for item in self._manifest(thread_id).artifacts if item.id == artifact_id),
            None,
        )
        if artifact is None:
            raise KeyError("unknown artifact")
        path = (directory / artifact.relative_path).resolve()
        if directory not in path.parents:
            raise ValueError("artifact path escapes workspace")
        return artifact, path.read_bytes()

    def export_zip(self, thread_id: str) -> bytes:
        manifest = self._manifest(thread_id)
        output = BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            manifest_bytes = manifest.model_dump_json(indent=2).encode()
            archive.writestr("manifest.json", manifest_bytes)
            archive.writestr(
                "exports/workspace.json",
                json.dumps(self.combined_export(thread_id), indent=2).encode(),
            )
            for artifact in manifest.artifacts:
                _, data = self.read_artifact(thread_id, artifact.id)
                archive.writestr(artifact.relative_path, data)
        return output.getvalue()

    def combined_export(self, thread_id: str) -> dict[str, Any]:
        """Return one structured export referencing every manifest artifact."""

        manifest = self._manifest(thread_id)
        contents: dict[str, Any] = {}
        for artifact in manifest.artifacts:
            if artifact.content_type == "application/json":
                _, data = self.read_artifact(thread_id, artifact.id)
                contents[artifact.id] = json.loads(data)
        return {
            "manifest": manifest.model_dump(mode="json"),
            "jsonArtifacts": contents,
        }

    def _thread_dir(self, thread_id: str) -> Path:
        if not _SAFE_ID.fullmatch(thread_id):
            raise ValueError("invalid thread ID")
        path = (self._root / thread_id).resolve()
        if self._root not in path.parents:
            raise ValueError("thread path escapes workspace root")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _manifest(self, thread_id: str) -> WorkspaceManifest:
        directory = self._thread_dir(thread_id)
        path = directory / "manifest.json"
        if path.exists():
            return WorkspaceManifest.model_validate_json(path.read_text())
        now = datetime.now(UTC)
        manifest = WorkspaceManifest(thread_id=thread_id, created_at=now, updated_at=now)
        self._save_manifest(directory, manifest)
        return manifest

    @staticmethod
    def _save_manifest(directory: Path, manifest: WorkspaceManifest) -> None:
        (directory / "manifest.json").write_text(manifest.model_dump_json(indent=2))

    @staticmethod
    def _safe_name(name: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(name).name).strip("-.")
        return cleaned or "artifact"
