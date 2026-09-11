"""Compatibility imports for source acquisition and adapter extraction."""

from mia_dpp.sources.extraction import (
    Crawl4AIPageLoader,
    Crawl4AIWebsiteExtractor,
    ExtractionDependencyError,
    HtmlEvidenceExtractor,
    PageLoader,
    PageLoadError,
    ProductUrlRejectedError,
    RenderedPage,
    RequiredEvidenceMissingError,
)

__all__ = [
    "Crawl4AIPageLoader",
    "Crawl4AIWebsiteExtractor",
    "ExtractionDependencyError",
    "HtmlEvidenceExtractor",
    "PageLoadError",
    "PageLoader",
    "ProductUrlRejectedError",
    "RenderedPage",
    "RequiredEvidenceMissingError",
]
