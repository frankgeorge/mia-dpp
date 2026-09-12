"""Acceptance tests for deterministic, approved website extraction."""

from __future__ import annotations

import asyncio
import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from mia_dpp.errors import ExtractionError
from mia_dpp.integrations.crawl4ai import Crawl4AIPageLoader
from mia_dpp.tools.web.adapter import (
    HtmlEvidenceExtractor,
)
from mia_dpp.tools.web.models import (
    ExtractionRule,
    ExtractionSource,
    ProductUrlRejectedError,
    RenderedPage,
    RequiredEvidenceMissingError,
    SiteAdapterSpec,
)

FIXTURES = Path(__file__).parent / "fixtures" / "web"
PRODUCT_URL = "https://manufacturer.example/products/pg-16"
ACQUIRED_AT = datetime(2026, 2, 3, 4, 5, 6, tzinfo=UTC)


def rule(
    predicate: str,
    source: ExtractionSource,
    selector: str,
    *,
    attribute: str | None = None,
    many: bool = False,
    required: bool = False,
    unit: str | None = None,
) -> ExtractionRule:
    return ExtractionRule(
        predicate=predicate,
        source=source,
        selector=selector,
        attribute=attribute,
        many=many,
        required=required,
        unit=unit,
    )


def site_spec(*rules: ExtractionRule, approved: bool = True) -> SiteAdapterSpec:
    return SiteAdapterSpec(
        id="manufacturer-products",
        version="1.0.0",
        site_origin="https://manufacturer.example",
        allowed_hosts=("manufacturer.example",),
        product_url_patterns=(r"/products/[a-z0-9-]+",),
        field_rules=rules,
        approved=approved,
    )


def fixture_page(name: str = "product.html", *, url: str = PRODUCT_URL) -> RenderedPage:
    return RenderedPage(
        url=url,
        html=(FIXTURES / name).read_text(encoding="utf-8"),
        acquired_at=ACQUIRED_AT,
    )


def test_extracts_css_xpath_meta_and_json_ld_with_provenance() -> None:
    spec = site_spec(
        rule(
            "product.designation",
            ExtractionSource.CSS,
            "h1[data-model]",
            attribute="data-model",
            required=True,
        ),
        rule(
            "manufacturer.name",
            ExtractionSource.XPATH,
            "//dd[@class='manufacturer']",
            required=True,
        ),
        rule(
            "document.description",
            ExtractionSource.META,
            "meta[name='description']",
        ),
        rule("product.name", ExtractionSource.JSON_LD, "/name", required=True),
        rule(
            "product.feature",
            ExtractionSource.CSS,
            "ul.features li",
            many=True,
        ),
    )

    page = fixture_page()
    evidence = HtmlEvidenceExtractor(spec).extract(page)

    assert [(item.predicate, item.value) for item in evidence] == [
        ("product.designation", "PG-16"),
        ("manufacturer.name", "MIA Manufacturing GmbH"),
        ("document.description", "A compact & efficient pressure gauge"),
        ("product.name", "Pressure Gauge PG-16"),
        ("product.feature", "IP65"),
        ("product.feature", "0\u201316 bar"),
    ]
    expected_hash = hashlib.sha256(page.html.encode("utf-8")).hexdigest()
    assert {item.source_content_sha256 for item in evidence} == {expected_hash}
    assert {item.source_uri for item in evidence} == {PRODUCT_URL}
    assert {item.acquired_at for item in evidence} == {ACQUIRED_AT}
    assert [item.extraction_method for item in evidence[:4]] == [
        "css",
        "xpath",
        "meta",
        "json_ld",
    ]
    assert evidence[3].source_location.json_pointer == "/name"
    assert evidence[3].source_location.selector == ("script[type='application/ld+json'] (match 1)")
    assert len({item.id for item in evidence}) == len(evidence)

    repeated = HtmlEvidenceExtractor(spec).extract(page)
    assert [item.id for item in repeated] == [item.id for item in evidence]


def test_json_ld_ignores_malformed_blocks_and_reads_graph_arrays() -> None:
    spec = site_spec(
        rule("product.name", ExtractionSource.JSON_LD, "/name", required=True),
        rule("product.code", ExtractionSource.JSON_LD, "/codes", many=True),
    )

    evidence = HtmlEvidenceExtractor(spec).extract(fixture_page("jsonld-graph.html"))

    assert [(item.predicate, item.value) for item in evidence] == [
        ("product.name", "Graph Product"),
        ("product.code", "A-1"),
        ("product.code", "B-2"),
    ]
    assert all("match 2" in (item.source_location.selector or "") for item in evidence)


def test_required_missing_value_fails_instead_of_inventing_evidence() -> None:
    spec = site_spec(
        rule(
            "product.serial",
            ExtractionSource.CSS,
            ".serial-number",
            required=True,
        )
    )

    with pytest.raises(RequiredEvidenceMissingError, match=r"product[.]serial"):
        HtmlEvidenceExtractor(spec).extract(fixture_page())


def test_optional_missing_value_is_omitted() -> None:
    spec = site_spec(
        rule("product.serial", ExtractionSource.CSS, ".serial-number"),
        rule("product.name", ExtractionSource.JSON_LD, "/name"),
    )

    evidence = HtmlEvidenceExtractor(spec).extract(fixture_page())

    assert [(item.predicate, item.value) for item in evidence] == [
        ("product.name", "Pressure Gauge PG-16")
    ]


def test_unapproved_adapter_cannot_extract() -> None:
    spec = site_spec(
        rule("product.name", ExtractionSource.CSS, "h1"),
        approved=False,
    )

    with pytest.raises(ExtractionError, match="must be approved"):
        HtmlEvidenceExtractor(spec)


@pytest.mark.parametrize(
    "url, message",
    [
        ("file:///etc/passwd", "absolute HTTP"),
        ("https://user:password@manufacturer.example/products/pg-16", "credentials"),
        ("https://attacker.example/products/pg-16", "not approved"),
        ("https://manufacturer.example/news/pg-16", "product URL pattern"),
    ],
)
def test_rejects_urls_outside_the_approved_product_scope(url: str, message: str) -> None:
    extractor = HtmlEvidenceExtractor(site_spec(rule("product.name", ExtractionSource.CSS, "h1")))

    with pytest.raises(ProductUrlRejectedError, match=message):
        extractor.extract(fixture_page(url=url))


def test_extract_url_validates_before_loading_and_checks_redirect_target() -> None:
    extractor = HtmlEvidenceExtractor(site_spec(rule("product.name", ExtractionSource.CSS, "h1")))

    class Loader:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def load(self, url: str) -> RenderedPage:
            self.calls.append(url)
            return fixture_page(url="https://attacker.example/products/stolen")

    loader = Loader()
    with pytest.raises(ProductUrlRejectedError, match="not approved"):
        asyncio.run(extractor.extract_url(PRODUCT_URL, loader))
    assert loader.calls == [PRODUCT_URL]

    untouched_loader = Loader()
    with pytest.raises(ProductUrlRejectedError, match="not approved"):
        asyncio.run(
            extractor.extract_url("https://attacker.example/products/stolen", untouched_loader)
        )
    assert untouched_loader.calls == []


def test_invalid_json_pointer_is_reported_as_a_configuration_error() -> None:
    spec = site_spec(rule("product.name", ExtractionSource.JSON_LD, "name"))

    with pytest.raises(ExtractionError, match="not a JSON Pointer"):
        HtmlEvidenceExtractor(spec).extract(fixture_page())


def test_rendered_page_requires_an_aware_acquisition_time() -> None:
    with pytest.raises(ValueError, match="timezone"):
        RenderedPage(
            url=PRODUCT_URL,
            html="<html></html>",
            acquired_at=ACQUIRED_AT.replace(tzinfo=None),
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
