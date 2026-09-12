"""Agent-facing deterministic document extraction capability."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol

from mia_dpp.canonical import sha256_json
from mia_dpp.domain.evidence import (
    DocumentReference,
    EvidenceRecord,
    EvidenceStatus,
    SourceLocation,
)
from mia_dpp.errors import ExtractionError


class TextPreprocessor(Protocol):
    """Small boundary implemented by a BaSyx PDF-to-AAS preprocessor."""

    def convert(self, filepath: str) -> list[str] | str | None: ...


class PdfToAasDocumentExtractor:
    """Convert PDF pages to provenance-rich evidence without invoking an LLM."""

    def __init__(self, preprocessor: TextPreprocessor) -> None:
        self._preprocessor = preprocessor

    def extract(self, document: DocumentReference) -> tuple[EvidenceRecord, ...]:
        """Return one text evidence record per non-empty PDF page."""

        path = Path(document.local_path)
        if not path.is_file():
            raise ExtractionError(f"document does not exist: {path}")
        actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_digest != document.content_sha256:
            raise ExtractionError("document content does not match its recorded SHA-256")
        converted = self._preprocessor.convert(str(path))
        if converted is None:
            raise ExtractionError("PDF-to-AAS preprocessor returned no content")
        pages = [converted] if isinstance(converted, str) else converted

        records: list[EvidenceRecord] = []
        for page_number, text in enumerate(pages, start=1):
            normalized = text.strip()
            if not normalized:
                continue
            identity = sha256_json(
                {
                    "document": document.content_sha256,
                    "page": page_number,
                    "text": normalized,
                }
            )
            records.append(
                EvidenceRecord(
                    id=f"ev-{identity[:24]}",
                    predicate="document.text",
                    value=normalized,
                    source_uri=document.uri,
                    source_content_sha256=document.content_sha256,
                    source_location=SourceLocation(
                        page=page_number,
                        excerpt=normalized[:240],
                    ),
                    extraction_method="pdf_text",
                    extractor_name="basyx-pdf-to-aas:PDFium",
                    extractor_version="1.0.0",
                    status=EvidenceStatus.OBSERVED,
                    acquired_at=document.acquired_at,
                )
            )
        return tuple(records)
