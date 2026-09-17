"""PDF-to-AAS/PDFium implementation of the document preprocessing boundary."""

from __future__ import annotations

from typing import cast

from mia_dpp.errors import ConfigurationError
from mia_dpp.tools.documents.tool import TextPreprocessor


class Pdf2AasTextPreprocessor:
    """Load the optional PDFium implementation only when this adapter is constructed."""

    def __init__(self) -> None:
        try:
            from pdf2aas.preprocessor import PDFium
        except ImportError as error:  # pragma: no cover - optional dependency
            raise ConfigurationError(
                "PDF extraction is optional; install the backend 'pdf' extra"
            ) from error
        self._delegate = cast(TextPreprocessor, PDFium())

    def convert(self, filepath: str) -> list[str] | str | None:
        return self._delegate.convert(filepath)
