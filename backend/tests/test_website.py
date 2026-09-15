"""Website ingestion tests without depending on a live external website."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mia_dpp.aas.build import build_dpp
from mia_dpp.aas.requirements import build_template_index
from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.agent.models import ProductWork
from mia_dpp.domain.mappings import FieldMapping, MappingStatus
from mia_dpp.errors import MappingError
from mia_dpp.tools.mapping.mapper import DeterministicWebsiteMapper
from mia_dpp.tools.web.generic import WebsiteFactExtractor
from mia_dpp.tools.web.models import ProductUrlRejectedError, RenderedPage
from mia_dpp.tools.web.tool import WebExtractionTool
from mia_dpp.tools.web.url_policy import ProductUrlPolicy

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


async def ingest(
    url: str = PRODUCT_URL,
    loader: FixtureLoader | None = None,
    *,
    template_keys: tuple[str, ...] = ("digital_nameplate", "technical_data"),
) -> ProductWork:
    repository = OfficialTemplateRepository()
    web_tool = WebExtractionTool(
        loader=loader or FixtureLoader(),
        url_policy=ProductUrlPolicy(public_resolver),
    )
    extraction = await web_tool.extract(url)
    index = build_template_index(tuple(repository.load(key) for key in template_keys))
    mapping = await DeterministicWebsiteMapper(repository).propose(extraction.evidence)
    work = ProductWork(
        product_id=extraction.product_id,
        product_name=extraction.product_name,
        source_urls=(extraction.evidence[0].source_uri,),
        source_artifact_ids=extraction.source_artifact_ids,
        evidence=extraction.evidence,
        mapping_result=mapping,
        template_index=index,
    )
    return work


def resolved_mappings(response: ProductWork) -> tuple[FieldMapping, ...]:
    assert response.mapping_result is not None
    result = response.mapping_result
    return (*result.mapped, *result.ambiguous, *result.rejected)


def test_generic_fact_extraction_retains_heterogeneous_source_facts() -> None:
    facts, product_name = WebsiteFactExtractor().extract(product_page())

    assert product_name == "Pressure Gauge PG-16"
    by_label = {item.source_label: item for item in facts}
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
    evidence, _ = WebsiteFactExtractor().extract(product_page())

    voltage = next(item for item in evidence if item.source_label == "Supply voltage")
    material = next(item for item in evidence if item.source_label == "Material")
    assert voltage.predicate == "source.supply.voltage"
    assert voltage.canonical_predicate is None
    assert material.predicate == "source.material"
    assert voltage.id != material.id


def test_website_service_maps_downstream_without_discarding_unmatched_evidence() -> None:
    loader = FixtureLoader()
    response = asyncio.run(ingest(loader=loader))

    assert loader.calls == [PRODUCT_URL]
    assert response.knowledge_package().product_name == "Pressure Gauge PG-16"
    assert len(response.knowledge_package().evidence) >= 18
    designation = next(
        item
        for item in resolved_mappings(response)
        if item.target.id_short == "ManufacturerProductDesignation"
    )
    assert designation.source_value == "PG-16"
    assert (
        next(
            item
            for item in response.knowledge_package().evidence
            if item.id == designation.evidence_id
        ).extraction_method
        == "json_ld"
    )
    targets = {item.target.id_short for item in resolved_mappings(response)}
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
    assert {item.source_uri for item in response.knowledge_package().evidence} == {PRODUCT_URL}
    assert {item.source_content_sha256 for item in response.knowledge_package().evidence} == {
        expected_hash
    }
    assert {item.acquired_at for item in response.knowledge_package().evidence} == {ACQUIRED_AT}
    assert all(item.id.startswith("ev-web-") for item in response.knowledge_package().evidence)
    order_code = next(
        item for item in response.knowledge_package().evidence if item.source_label == "SKU"
    )
    assert order_code.source_location.json_pointer == "/sku"

    mapped_ids = {
        item.evidence_id
        for item in (*response.mapping_result.mapped, *response.mapping_result.ambiguous)
    }
    unknown = {
        item.source_label: item.id
        for item in response.knowledge_package().evidence
        if item.source_label in {"Processor", "Protocol", "Material"}
    }
    assert set(unknown) == {"Processor", "Protocol", "Material"}
    assert set(unknown.values()) <= set(response.mapping_result.unmatched_evidence_ids)
    assert mapped_ids.isdisjoint(response.mapping_result.unmatched_evidence_ids)
    assert len(response.mapping_result.unmatched_evidence_ids) > len(mapped_ids)

    coverage = response.coverage_report
    assert [item.key for item in coverage.inventory.selected_templates] == [
        "digital_nameplate",
        "technical_data",
    ]
    assert coverage.analyzed_evidence_ids == tuple(
        item.id for item in response.knowledge_package().evidence
    )
    assert coverage.statistics.selected_templates == 2
    assert coverage.statistics.requirements == len(coverage.coverage) == 79
    assert coverage.statistics.required_requirements == 9
    required_values = [
        item
        for item in coverage.inventory.requirements
        if item.required and item.kind.value == "value" and not item.wildcard
    ]
    assert sum(item.template_key == "digital_nameplate" for item in required_values) == 4
    assert sum(item.template_key == "technical_data" for item in required_values) == 4


def test_completion_never_counts_structure_or_wildcards_as_missing_fields() -> None:
    response = asyncio.run(ingest())
    inventory = response.coverage_report.inventory.requirements
    fixed_count = sum(item.kind.value == "value" and not item.wildcard for item in inventory)

    assert fixed_count < len(inventory)
    assert all(
        item.id_short != "ArbitraryProperty"
        for item in inventory
        if item.kind.value == "value" and not item.wildcard
    )


def test_website_coverage_accepts_an_explicit_template_selection() -> None:
    response = asyncio.run(ingest(template_keys=("technical_data",)))

    assert [item.key for item in response.coverage_report.inventory.selected_templates] == [
        "technical_data"
    ]
    assert response.coverage_report.statistics.selected_templates == 1
    assert response.coverage_report.statistics.requirements == 48


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

    response = asyncio.run(ingest(loader=RepeatedValueLoader()))

    order_code = next(
        item
        for item in response.knowledge_package().evidence
        if item.source_label == "Article number"
    )
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

    response = asyncio.run(ingest(loader=UnmappedLoader()))

    technical = [
        item
        for item in response.knowledge_package().evidence
        if item.source_label
        in {"Processor", "Protocol", "Material", "Supply voltage", "Rated current", "Weight"}
    ]
    assert len(technical) == 6
    assert len({item.id for item in technical}) == 6
    assert {item.id for item in technical} <= set(response.mapping_result.unmatched_evidence_ids)


def test_repeated_technical_concepts_keep_component_context() -> None:
    page = RenderedPage(
        url=PRODUCT_URL,
        html="""
        <html><head><title>Controller</title></head><body>
          <table><caption>Probe</caption>
            <tr><th>Degree of protection</th><td>IP68</td></tr>
          </table>
          <table><caption>Control unit</caption>
            <tr><th>Degree of protection</th><td>IP54</td></tr>
          </table>
        </body></html>
        """,
        acquired_at=ACQUIRED_AT,
    )
    facts, _ = WebsiteFactExtractor().extract(page)
    protection = [item for item in facts if item.source_label == "Degree of protection"]

    assert [(item.value, item.source_location.table) for item in protection] == [
        ("IP68", "Probe"),
        ("IP54", "Control unit"),
    ]


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

    response = asyncio.run(ingest(loader=FooterLoader()))

    assert "YearOfConstruction" not in {
        item.target.id_short for item in resolved_mappings(response)
    }


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

    response = asyncio.run(ingest(loader=FactorySettingLoader()))

    assert "ManufacturingSite" not in {item.target.id_short for item in resolved_mappings(response)}


def test_website_evidence_survives_review_and_aas_compilation() -> None:
    response = asyncio.run(ingest())
    accepted = [
        mapping.model_copy(update={"id": f"mapping-{index}", "status": MappingStatus.APPROVED})
        for index, mapping in enumerate(resolved_mappings(response))
        if mapping.target.id_short != "MarkingName"
    ]

    package = build_dpp(
        response.knowledge_package().product_name,
        accepted,
        evidence=response.knowledge_package().evidence,
        now=ACQUIRED_AT,
    )

    assert package.deployable
    assert package.validation_report.valid
    assert package.evidence
    assert {item.source_uri for item in package.evidence} == {PRODUCT_URL}


def test_compiler_rejects_a_website_mapping_without_its_evidence() -> None:
    response = asyncio.run(ingest())
    mapping = resolved_mappings(response)[0]
    accepted = mapping.model_copy(
        update={
            "id": "mapping-with-missing-evidence",
            "status": MappingStatus.APPROVED,
        }
    )

    with pytest.raises(MappingError, match="missing supplied evidence"):
        build_dpp(
            response.knowledge_package().product_name,
            [accepted],
            evidence=tuple(
                item
                for item in response.knowledge_package().evidence
                if item.id != mapping.evidence_id
            ),
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

    web_tool = WebExtractionTool(
        loader=FixtureLoader("http://localhost/internal"),
        url_policy=ProductUrlPolicy(resolver),
    )
    with pytest.raises(ProductUrlRejectedError, match="private"):
        asyncio.run(web_tool.extract(PRODUCT_URL))
