"""Crawl4AI implementation of MIA's provider-neutral page loader."""

from __future__ import annotations

from urllib.parse import urlsplit

from mia_dpp.tools.web.models import (
    ExtractionDependencyError,
    PageLoadError,
    RenderedPage,
    SourceLink,
)


class Crawl4AIPageLoader:
    """Render public pages through Crawl4AI for ``WebExtractionTool``.

    ``Mia`` injects this concrete integration through the provider-neutral
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

    async def discover(self, url: str) -> tuple[SourceLink, ...]:
        """Run a small same-domain native deep crawl for related source pages."""

        try:
            from crawl4ai import AsyncWebCrawler, BFSDeepCrawlStrategy, CrawlerRunConfig
            from crawl4ai.deep_crawling.filters import DomainFilter, FilterChain, URLPatternFilter
            from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
        except ImportError as exc:  # pragma: no cover - optional installation
            raise ExtractionDependencyError(
                "Crawl4AI is not installed; install the crawl runtime to discover sources"
            ) from exc

        host = urlsplit(url).hostname or ""
        strategy = BFSDeepCrawlStrategy(
            max_depth=2,
            max_pages=12,
            include_external=False,
            filter_chain=FilterChain(
                [
                    DomainFilter(allowed_domains=[host]),
                    URLPatternFilter(
                        patterns=[
                            "*login*",
                            "*cart*",
                            "*privacy*",
                            "*legal*",
                            "*imprint*",
                            "*facebook*",
                            "*instagram*",
                            "*linkedin*",
                        ],
                        reverse=True,
                    ),
                ]
            ),
            url_scorer=KeywordRelevanceScorer(
                keywords=["product", "technical", "datasheet", "download", "document"]
            ),
        )
        try:
            async with AsyncWebCrawler() as crawler:
                results = await crawler.arun(
                    url=url,
                    config=CrawlerRunConfig(deep_crawl_strategy=strategy, stream=False),
                )
        except Exception as exc:  # pragma: no cover - browser/upstream failure
            raise PageLoadError(f"Crawl4AI could not discover sources from {url!r}: {exc}") from exc

        return tuple(
            SourceLink(
                url=str(result.url),
                text=str(getattr(result, "metadata", {}).get("title") or ""),
            )
            for result in results
            if getattr(result, "success", False)
            and getattr(result, "url", None)
            and str(result.url) != url
        )
