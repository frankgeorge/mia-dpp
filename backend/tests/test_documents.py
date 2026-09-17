"""Tests for the isolated BaSyx PDF-to-AAS preprocessing boundary."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mia_dpp.domain.evidence import DocumentReference
from mia_dpp.errors import ExtractionError
from mia_dpp.tools.documents.tool import PdfToAasDocumentExtractor


class FakePreprocessor:
    def __init__(self, result: list[str] | str | None) -> None:
        self.result = result

    def convert(self, filepath: str) -> list[str] | str | None:
        assert filepath.endswith("fixture.pdf")
        return self.result


def reference(path: Path, *, digest: str | None = None) -> DocumentReference:
    return DocumentReference(
        uri="https://manufacturer.example/fixture.pdf",
        local_path=str(path),
        content_sha256=digest or hashlib.sha256(path.read_bytes()).hexdigest(),
        media_type="application/pdf",
        acquired_at=datetime(2026, 2, 3, tzinfo=UTC),
    )


def test_converts_pages_to_traceable_evidence(tmp_path: Path) -> None:
    path = tmp_path / "fixture.pdf"
    path.write_bytes(b"fixture")
    extractor = PdfToAasDocumentExtractor(FakePreprocessor([" page one ", "", "page three"]))

    evidence = extractor.extract(reference(path))

    assert [item.value for item in evidence] == ["page one", "page three"]
    assert [item.source_location.page for item in evidence] == [1, 3]
    assert all(item.source_uri.endswith("fixture.pdf") for item in evidence)


def test_rejects_changed_document_content(tmp_path: Path) -> None:
    path = tmp_path / "fixture.pdf"
    path.write_bytes(b"changed")

    with pytest.raises(ExtractionError, match="SHA-256"):
        PdfToAasDocumentExtractor(FakePreprocessor("text")).extract(
            reference(path, digest="0" * 64)
        )


def test_rejects_missing_document(tmp_path: Path) -> None:
    missing = tmp_path / "fixture.pdf"
    document = DocumentReference(
        uri="https://manufacturer.example/fixture.pdf",
        local_path=str(missing),
        content_sha256="0" * 64,
        media_type="application/pdf",
    )

    with pytest.raises(ExtractionError, match="does not exist"):
        PdfToAasDocumentExtractor(FakePreprocessor("text")).extract(document)
