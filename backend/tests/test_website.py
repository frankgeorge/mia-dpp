"""Website ingestion tests without depending on a live external website."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mia_dpp.errors import MappingError
from mia_dpp.evidence import EvidenceNormalizer
from mia_dpp.extraction import ProductUrlRejectedError, RenderedPage
from mia_dpp.models import FieldMapping, MappingStatus, WebsiteIngestRequest
from mia_dpp.pipeline import build_dpp
from mia_dpp.source_artifacts import raw_website_artifact
from mia_dpp.templates import OfficialTemplateRepository
from mia_dpp.url_policy import ProductUrlPolicy
from mia_dpp.website import WebsiteIngestionService
from mia_dpp.website_facts import WebsiteFactExtractor

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


def test_generic_fact_extraction_retains_heterogeneous_source_facts() -> None:
    source = raw_website_artifact(product_page())
    facts, product_name = WebsiteFactExtractor().extract(source)

    assert product_name == "Pressure Gauge PG-16"
    by_label = {item.label: item for item in facts}
    assert {
        "Manufacturer",
        "Model",
        "Processor",
        "Supply voltage",
        "Rated current",
        "Operating temperature",
        "Weight",
        "Dimensions",
        "Protocol",
        "Material",
        "Protection class",
    } <= by_label.keys()
    assert len(facts) >= 18
    assert by_label["Supply voltage"].unit == "V"
    manufacturer = by_label["Manufacturer"]
    measuring_range = by_label["Measuring range"]
    assert manufacturer.source_location.json_pointer == "/manufacturer"
    assert measuring_range.source_location.selector == "table:nth-of-type(1) tr:nth-of-type(1)"
    assert measuring_range.source_location.table == "Technical specifications"


def test_normalization_keeps_source_labels_separate_from_semantics() -> None:
    source = raw_website_artifact(product_page())
    facts, _ = WebsiteFactExtractor().extract(source)
    evidence = EvidenceNormalizer().normalize(source, facts)

    voltage = next(item for item in evidence if item.source_label == "Supply voltage")
    material = next(item for item in evidence if item.source_label == "Material")
    assert voltage.predicate == "source.supply.voltage"
    assert voltage.canonical_predicate is None
    assert material.predicate == "source.material"
    assert voltage.id != material.id


def test_website_service_maps_downstream_without_discarding_unmatched_evidence() -> None:
    loader = FixtureLoader()
    response = asyncio.run(service(loader).ingest(WebsiteIngestRequest(url=PRODUCT_URL)))

    assert loader.calls == [PRODUCT_URL]
    assert response.mode == "website"
    assert response.proposal.product_name == "Pressure Gauge PG-16"
    assert response.knowledge_package.evidence == response.evidence
    assert len(response.evidence) >= 18
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
    order_code = next(item for item in response.evidence if item.source_label == "SKU")
    assert order_code.source_location.json_pointer == "/sku"

    mapped_ids = {
        item.evidence_id
        for item in (*response.mapping_result.mapped, *response.mapping_result.ambiguous)
    }
    unknown = {
        item.source_label: item.id
        for item in response.evidence
        if item.source_label in {"Processor", "Protocol", "Material"}
    }
    assert set(unknown) == {"Processor", "Protocol", "Material"}
    assert set(unknown.values()) <= set(response.mapping_result.unmatched_evidence_ids)
    assert mapped_ids.isdisjoint(response.mapping_result.unmatched_evidence_ids)
    assert len(response.mapping_result.unmatched_evidence_ids) > len(mapped_ids)

    assert [event.stage for event in response.workflow_events] == [
        "source.fetch",
        "facts.extract",
        "evidence.normalize",
        "mapping.deterministic",
    ]
    assert response.workflow_events[1].output_count == len(response.evidence)
    mapping_event = response.workflow_events[-1]
    assert mapping_event.input_count == len(response.evidence)
    assert mapping_event.metadata["unmatched"] == len(
        response.mapping_result.unmatched_evidence_ids
    )


def test_same_value_is_not_attached_to_the_wrong_json_ld_field() -> None:
    page = RenderedPage(
        url=PRODUCT_URL,
        html="""
        <html><head><script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Product","name":"PN7094",
         "manufacturer":{"name":"Example Instruments GmbH"}}
        </script></head><body>
          <dl><dt>Article number</dt><dd>PN7094</dd></dl>
        </body></html>
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

    order_code = next(item for item in response.evidence if item.source_label == "Article number")
    assert order_code.source_location.selector == "dt:nth-of-type(1)"
    assert order_code.source_location.json_pointer is None


def test_mapping_failure_never_deletes_or_collapses_evidence() -> None:
    page = RenderedPage(
        url=PRODUCT_URL,
        html="""
        <html><head><title>Controller X</title></head><body>
          <h1>Controller X</h1>
          <table>
            <tr><th>Processor</th><td>PSoC 6</td></tr>
            <tr><th>Protocol</th><td>PROFINET</td></tr>
            <tr><th>Material</th><td>Aluminium</td></tr>
            <tr><th>Supply voltage</th><td>24 V</td></tr>
            <tr><th>Rated current</th><td>2.3 A</td></tr>
            <tr><th>Weight</th><td>8.2 kg</td></tr>
          </table>
        </body></html>
        """,
        acquired_at=ACQUIRED_AT,
    )

    class UnmappedLoader:
        async def load(self, url: str) -> RenderedPage:
            return page

    response = asyncio.run(
        WebsiteIngestionService(
            OfficialTemplateRepository(),
            loader=UnmappedLoader(),
            url_policy=ProductUrlPolicy(public_resolver),
        ).ingest(WebsiteIngestRequest(url=PRODUCT_URL))
    )

    technical = [
        item
        for item in response.evidence
        if item.source_label
        in {"Processor", "Protocol", "Material", "Supply voltage", "Rated current", "Weight"}
    ]
    assert len(technical) == 6
    assert len({item.id for item in technical}) == 6
    assert {item.id for item in technical} <= set(response.mapping_result.unmatched_evidence_ids)
    assert response.knowledge_package.evidence == response.evidence


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
        if mapping.target_element != "MarkingName"
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
            evidence=tuple(item for item in response.evidence if item.id != mapping.evidence_id),
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
