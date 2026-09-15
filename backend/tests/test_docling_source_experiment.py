from __future__ import annotations

from datetime import UTC, datetime

from mia_dpp.experiments.docling_source import (
    DoclingSourceNormalizer,
    lean_llm_view,
    lean_view_markdown,
)
from mia_dpp.tools.web.models import RenderedPage


def _page(html: str) -> RenderedPage:
    return RenderedPage(
        url="https://manufacturer.example/products/pump",
        html=html,
        acquired_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_docling_normalizes_rendered_html_without_recrawling() -> None:
    page = _page(
        """
        <html><body><h1>Pump 20</h1><h2>Technical data</h2>
        <dl><dt>Operating temperature</dt><dd><dl>
        <dt>Medium</dt><dd>-5/+70 °C</dd>
        </dl></dd></dl></body></html>
        """
    )

    document = DoclingSourceNormalizer().normalize(page)
    exported = document.export_to_dict()

    assert str(document.origin.uri) == page.url
    assert exported["texts"][0]["text"] == "Pump 20"
    assert all(item.get("prov") == [] for item in exported["texts"])


def test_lean_view_preserves_hierarchy_and_omits_heavy_provenance() -> None:
    page = _page(
        """
        <h1>Pump 20</h1><h2>Technical data</h2>
        <dl><dt>Operating temperature</dt><dd><dl>
        <dt>Medium</dt><dd>-5/+70 °C</dd>
        </dl></dd></dl>
        """
    )
    document = DoclingSourceNormalizer().normalize(page)

    view = lean_llm_view(document, source_url=page.url)
    payload = view.model_dump(mode="json")
    serialized = view.model_dump_json()

    technical = payload["items"][0]["children"][0]
    operating = technical["children"][0]
    assert operating["text"] == "Operating temperature"
    assert operating["children"][0]["text"] == "Medium"
    assert operating["children"][0]["children"][0]["text"] == "-5/+70 °C"
    assert "prov" not in serialized
    assert "sha256" not in serialized
    assert "selector" not in serialized
    assert '"source_item_id":"#/texts/' in serialized

    repeated = lean_llm_view(document, source_url=page.url)
    assert repeated.items[0].source_item_id == view.items[0].source_item_id


def test_lean_view_retains_table_cells() -> None:
    page = _page(
        """
        <h1>Pump 20</h1><h2>Specifications</h2>
        <table><tr><th>Property</th><th>Value</th></tr>
        <tr><td>Protection</td><td>IP65</td></tr></table>
        """
    )
    document = DoclingSourceNormalizer().normalize(page)

    view = lean_llm_view(document, source_url=page.url)
    markdown = lean_view_markdown(view)

    table = view.items[0].children[0].children[0]
    assert table.rows == [["Property", "Value"], ["Protection", "IP65"]]
    assert "Protection | IP65" in markdown
