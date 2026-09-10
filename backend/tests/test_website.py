"""Website ingestion tests without depending on a live external website."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mia_dpp.errors import MappingError
from mia_dpp.extraction import ProductUrlRejectedError, RenderedPage
from mia_dpp.models import FieldMapping, MappingStatus, WebsiteIngestRequest
from mia_dpp.pipeline import build_dpp
from mia_dpp.templates import OfficialTemplateRepository
from mia_dpp.url_policy import ProductUrlPolicy
from mia_dpp.website import ProductPageText, WebsiteIngestionService

FIXTURE = Path(__file__).parent / "fixtures" / "web" / "website-product.html"
PRODUCT_URL = "https://manufacturer.example/products/pg-16"
ACQUIRED_AT = datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC)


async def public_resolver(host: str, port: int) -> tuple[str, ...]:
    assert host
    assert port in {80, 443}
    return ("93.184.216.34",)


def product_page(url: str = PRODUCT_URL) -> RenderedPage:
    return RenderedPage(
        url=url,
        html=FIXTURE.read_text(encoding="utf-8"),
        acquired_at=ACQUIRED_AT,
    )


class FixtureLoader:
    def __init__(self, final_url: str = PRODUCT_URL) -> None:
        self.final_url = final_url
        self.calls: list[str] = []

    async def load(self, url: str) -> RenderedPage:
        self.calls.append(url)
        return product_page(self.final_url)


def service(loader: FixtureLoader | None = None) -> WebsiteIngestionService:
    return WebsiteIngestionService(
        OfficialTemplateRepository(),
        loader=loader or FixtureLoader(),
        url_policy=ProductUrlPolicy(public_resolver),
    )


def test_structured_page_text_keeps_json_pointer_and_table_location() -> None:
    text, signals, product_name = ProductPageText().extract(product_page())

    assert product_name == "Pressure Gauge PG-16"
    assert "manufacturer: Example Instruments GmbH" in text
    assert "Measuring range: 0\u201316 bar" in text
    manufacturer = next(item for item in signals if item.label == "manufacturer")
    measuring_range = next(item for item in signals if item.label == "Measuring range")
    assert manufacturer.location.json_pointer == "/manufacturer"
    assert measuring_range.location.selector == "tr:nth-of-type(1)"


def test_website_service_reuses_mapping_logic_and_rewrites_provenance() -> None:
    loader = FixtureLoader()
    response = asyncio.run(service(loader).ingest(WebsiteIngestRequest(url=PRODUCT_URL)))

    assert loader.calls == [PRODUCT_URL]
    assert response.mode == "website"
    assert response.proposal.product_name == "Pressure Gauge PG-16"
    designation = next(
        item
        for item in response.proposal.mappings
        if item.target_element == "ManufacturerProductDesignation"
    )
    assert designation.source_value == "PG-16"
    assert (
        next(
            item for item in response.evidence if item.id == designation.evidence_id
        ).extraction_method
        == "json_ld"
    )
    targets = {item.target_element for item in response.proposal.mappings}
    assert {
        "ManufacturerName",
        "ManufacturerProductDesignation",
        "SerialNumber",
        "OrderCodeOfManufacturer",
        "YearOfConstruction",
        "CountryOfOrigin",
        "DegreeOfProtection",
        "MeasuringRange",
    } <= targets
    expected_hash = hashlib.sha256(product_page().html.encode()).hexdigest()
    assert {item.source_uri for item in response.evidence} == {PRODUCT_URL}
    assert {item.source_content_sha256 for item in response.evidence} == {expected_hash}
    assert {item.acquired_at for item in response.evidence} == {ACQUIRED_AT}
    assert all(item.id.startswith("ev-web-") for item in response.evidence)
    order_code = next(item for item in response.evidence if item.predicate == "product.order_code")
    assert order_code.source_location.json_pointer == "/sku"


def test_same_value_is_not_attached_to_the_wrong_json_ld_field() -> None:
    page = RenderedPage(
        url=PRODUCT_URL,
        html="""
        <html><head><script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Product","name":"PN7094",
         "manufacturer":{"name":"Example Instruments GmbH"}}
        </script></head><body><p>Article number: PN7094</p></body></html>
        """,
        acquired_at=ACQUIRED_AT,
    )

    class RepeatedValueLoader:
        async def load(self, url: str) -> RenderedPage:
            return page

    response = asyncio.run(
        WebsiteIngestionService(
            OfficialTemplateRepository(),
            loader=RepeatedValueLoader(),
            url_policy=ProductUrlPolicy(public_resolver),
        ).ingest(WebsiteIngestRequest(url=PRODUCT_URL))
    )

    order_code = next(item for item in response.evidence if item.predicate == "product.order_code")
    assert order_code.source_location.selector == "body"
    assert order_code.source_location.json_pointer is None


def test_website_does_not_treat_footer_year_as_construction_year() -> None:
    page = RenderedPage(
        url=PRODUCT_URL,
        html="""
        <html><body>
          <h1>Gauge PG-16</h1>
          <dl><dt>Manufacturer</dt><dd>Example Instruments GmbH</dd></dl>
          <footer>Copyright 2022 Example Instruments GmbH</footer>
        </body></html>
        """,
        acquired_at=ACQUIRED_AT,
    )

    class FooterLoader:
        async def load(self, url: str) -> RenderedPage:
            return page

    response = asyncio.run(
        WebsiteIngestionService(
            OfficialTemplateRepository(),
            loader=FooterLoader(),
            url_policy=ProductUrlPolicy(public_resolver),
        ).ingest(WebsiteIngestRequest(url=PRODUCT_URL))
    )

    assert "YearOfConstruction" not in {item.target_element for item in response.proposal.mappings}


def test_website_does_not_treat_factory_setting_as_manufacturing_site() -> None:
    page = RenderedPage(
        url=PRODUCT_URL,
        html="""
        <html><body>
          <h1>Gauge PG-16</h1>
          <dl><dt>Manufacturer</dt><dd>Example Instruments GmbH</dd></dl>
          <p>Factory setting: normally open</p>
        </body></html>
        """,
        acquired_at=ACQUIRED_AT,
    )

    class FactorySettingLoader:
        async def load(self, url: str) -> RenderedPage:
            return page

    response = asyncio.run(
        WebsiteIngestionService(
            OfficialTemplateRepository(),
            loader=FactorySettingLoader(),
            url_policy=ProductUrlPolicy(public_resolver),
        ).ingest(WebsiteIngestRequest(url=PRODUCT_URL))
    )

    assert "ManufacturingSite" not in {item.target_element for item in response.proposal.mappings}


def test_website_evidence_survives_review_and_aas_compilation() -> None:
    response = asyncio.run(service().ingest(WebsiteIngestRequest(url=PRODUCT_URL)))
    accepted = [
        FieldMapping(
            **mapping.model_dump(exclude={"status"}),
            id=f"mapping-{index}",
            status=MappingStatus.APPROVED,
        )
        for index, mapping in enumerate(response.proposal.mappings)
    ]

    package = build_dpp(
        response.proposal.product_name,
        accepted,
        evidence=response.evidence,
        now=ACQUIRED_AT,
    )

    assert package.deployable
    assert package.validation_report.valid
    assert package.evidence
    assert {item.source_uri for item in package.evidence} == {PRODUCT_URL}


def test_compiler_rejects_a_website_mapping_without_its_evidence() -> None:
    response = asyncio.run(service().ingest(WebsiteIngestRequest(url=PRODUCT_URL)))
    mapping = response.proposal.mappings[0]
    accepted = FieldMapping(
        **mapping.model_dump(exclude={"status"}),
        id="mapping-with-missing-evidence",
        status=MappingStatus.APPROVED,
    )

    with pytest.raises(MappingError, match="missing supplied evidence"):
        build_dpp(
            response.proposal.product_name,
            [accepted],
            evidence=response.evidence[1:],
            now=ACQUIRED_AT,
        )


@pytest.mark.parametrize(
    "url,addresses,message",
    [
        ("file:///etc/passwd", ("93.184.216.34",), "absolute HTTP"),
        ("https://user:secret@example.com/product", ("93.184.216.34",), "credentials"),
        ("http://127.0.0.1/admin", ("127.0.0.1",), "private"),
        ("http://example.com:8080/product", ("93.184.216.34",), "port 80 or 443"),
    ],
)
def test_url_policy_rejects_unsafe_targets(
    url: str,
    addresses: tuple[str, ...],
    message: str,
) -> None:
    async def resolver(host: str, port: int) -> tuple[str, ...]:
        return addresses

    with pytest.raises(ProductUrlRejectedError, match=message):
        asyncio.run(ProductUrlPolicy(resolver).validate(url))


def test_service_checks_the_final_crawl4ai_url() -> None:
    async def resolver(host: str, port: int) -> tuple[str, ...]:
        return ("127.0.0.1",) if host == "localhost" else ("93.184.216.34",)

    ingestion = WebsiteIngestionService(
        OfficialTemplateRepository(),
        loader=FixtureLoader("http://localhost/internal"),
        url_policy=ProductUrlPolicy(resolver),
    )

    with pytest.raises(ProductUrlRejectedError, match="private"):
        asyncio.run(ingestion.ingest(WebsiteIngestRequest(url=PRODUCT_URL)))
