"""Crawl4AI implementation of MIA's provider-neutral page loader."""

from __future__ import annotations

from mia_dpp.tools.web.models import ExtractionDependencyError, PageLoadError, RenderedPage


class Crawl4AIPageLoader:
    """Render public pages through Crawl4AI for ``WebExtractionTool``.

    ``bootstrap`` injects this concrete integration through the provider-neutral
    ``PageLoader`` boundary; it returns HTML and the final redirected URL.
    """

    async def load(self, url: str) -> RenderedPage:
        """Render one URL or raise a web-tool error the agent/API can handle."""

        try:
            from crawl4ai import AsyncWebCrawler
        except ImportError as exc:  # pragma: no cover - optional installation
            raise ExtractionDependencyError(
                "Crawl4AI is not installed; install the crawl runtime to load live pages"
            ) from exc

        try:
            async with AsyncWebCrawler() as crawler:
                result = await crawler.arun(url=url)
        except Exception as exc:  # pragma: no cover - browser/upstream failure
            raise PageLoadError(f"Crawl4AI could not load {url!r}: {exc}") from exc

        if not getattr(result, "success", False):
            detail = getattr(result, "error_message", None) or "unknown crawler error"
            raise PageLoadError(f"Crawl4AI could not load {url!r}: {detail}")
        html = getattr(result, "html", None)
        if not isinstance(html, str) or not html:
            raise PageLoadError(f"Crawl4AI returned no HTML for {url!r}")
        final_url = getattr(result, "redirected_url", None) or getattr(result, "url", None)
        return RenderedPage(
            url=final_url if isinstance(final_url, str) and final_url else url,
            html=html,
        )
