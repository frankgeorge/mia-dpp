"""Tests for the provider boundary used by live web extraction."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from mia_dpp.integrations.crawl4ai import Crawl4AIPageLoader
from mia_dpp.tools.web.models import RenderedPage

PRODUCT_URL = "https://manufacturer.example/products/pg-16"


def test_rendered_page_requires_an_aware_acquisition_time() -> None:
    with pytest.raises(ValueError, match="timezone"):
        RenderedPage(
            url=PRODUCT_URL,
            html="<html></html>",
            acquired_at=datetime(2026, 2, 3, 4, 5, 6, tzinfo=UTC).replace(tzinfo=None),
        )


def test_crawl4ai_loader_converts_upstream_result_and_keeps_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCrawler:
        async def __aenter__(self) -> FakeCrawler:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def arun(self, *, url: str) -> SimpleNamespace:
            return SimpleNamespace(
                success=True,
                html="<html><h1>Product</h1></html>",
                url=url,
                redirected_url="https://manufacturer.example/products/final",
            )

    monkeypatch.setitem(sys.modules, "crawl4ai", SimpleNamespace(AsyncWebCrawler=FakeCrawler))

    page = asyncio.run(Crawl4AIPageLoader().load(PRODUCT_URL))

    assert page.url == "https://manufacturer.example/products/final"
    assert page.html == "<html><h1>Product</h1></html>"
