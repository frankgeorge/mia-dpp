from __future__ import annotations

from datetime import UTC, datetime

from scripts.compare_source_normalizers import (
    docling_lean_relationship,
    docling_native_relationship,
    table_metrics,
    unstructured_lean_relationship,
    unstructured_native_relationship,
)

from mia_dpp.experiments.docling_source import DoclingSourceNormalizer, lean_llm_view
from mia_dpp.experiments.unstructured_source import (
    UnstructuredSourcePartitioner,
    canonical_elements,
    lean_unstructured_view,
)
from mia_dpp.tools.web.models import RenderedPage


def _page(html: str) -> RenderedPage:
    return RenderedPage(
        url="https://manufacturer.example/products/controller",
        html=html,
        acquired_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_unstructured_partitions_supplied_html_with_native_metadata() -> None:
    page = _page("<h1>Controller</h1><h2>Specifications</h2><p>Runs continuously.</p>")

    elements = UnstructuredSourcePartitioner().partition(page)
    canonical = canonical_elements(elements)

    assert [element["type"] for element in canonical] == [
        "Title",
        "Title",
        "UncategorizedText",
    ]
    assert all(element["metadata"]["url"] == page.url for element in canonical)
    assert all(element["metadata"]["filename"] == "rendered-page.html" for element in canonical)
    assert canonical[1]["metadata"]["parent_id"] == canonical[0]["element_id"]


def test_lean_view_retains_parent_ids_and_table_rows_without_heavy_html() -> None:
    page = _page(
        """
        <h1>Controller</h1><h2>Specifications</h2>
        <table><tr><th>Property</th><th>Value</th></tr>
        <tr><td>Protection</td><td>IP65</td></tr></table>
        """
    )
    elements = UnstructuredSourcePartitioner().partition(page)

    view = lean_unstructured_view(elements, source_url=page.url)
    payload = view.model_dump_json(exclude_none=True, exclude_defaults=True)
    table = next(element for element in view.elements if element.kind == "Table")

    assert table.table_rows == [["Property", "Value"], ["Protection", "IP65"]]
    assert table.parent_id is not None
    assert "text_as_html" not in payload
    assert "coordinates" not in payload
    assert table.source_element_id in payload


def test_comparison_checks_native_and_lean_hierarchy_independently() -> None:
    page = _page(
        """
        <h1>Controller</h1><h2>Specifications</h2>
        <h3>Housing</h3><p>Degree of protection IP65.</p>
        """
    )
    docling = DoclingSourceNormalizer().normalize(page)
    docling_lean = lean_llm_view(docling, source_url=page.url)
    elements = UnstructuredSourcePartitioner().partition(page)
    unstructured_lean = lean_unstructured_view(elements, source_url=page.url)

    assert docling_native_relationship(docling, "Housing", "IP65")
    assert docling_lean_relationship(docling_lean, "Housing", "IP65")
    assert unstructured_native_relationship(elements, "Housing", "IP65")
    assert unstructured_lean_relationship(unstructured_lean, "Housing", "IP65")


def test_table_comparison_reports_structure_for_both_libraries() -> None:
    page = _page(
        """
        <h1>Controller</h1><table><tr><th colspan="2">Specifications</th></tr>
        <tr><td>Protection</td><td>IP65</td></tr></table>
        """
    )
    docling = DoclingSourceNormalizer().normalize(page)
    elements = UnstructuredSourcePartitioner().partition(page)

    metrics = table_metrics(page.html, docling, elements)

    assert metrics["source_html_tables"] == 1
    assert metrics["docling_tables"] == 1
    assert metrics["unstructured_tables"] == 1
    assert metrics["docling_header_cells"] >= 1
    assert metrics["source_spanned_cells"] == 1
