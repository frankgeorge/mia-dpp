"""Compare Docling and Unstructured using identical rendered HTML snapshots."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.items.node import NodeItem
from unstructured.documents.elements import Element

from mia_dpp.experiments.docling_source import (
    DoclingSourceNormalizer,
    LeanSourceNode,
    LeanSourceView,
    lean_llm_view,
    lean_view_markdown,
)
from mia_dpp.experiments.source_benchmarks import BENCHMARK_PAGES, BenchmarkPage
from mia_dpp.experiments.unstructured_source import (
    UnstructuredLeanElement,
    UnstructuredLeanView,
    UnstructuredSourcePartitioner,
    canonical_elements,
    lean_unstructured_markdown,
    lean_unstructured_view,
)
from mia_dpp.integrations.crawl4ai import Crawl4AIPageLoader
from mia_dpp.tools.web.models import RenderedPage


async def compare(page: BenchmarkPage, input_root: Path, output_root: Path) -> dict[str, Any]:
    """Run both normalizers against one shared HTML snapshot and save their outputs."""

    print(f"\nNormalizing: {page.label}", flush=True)
    rendered = await _load_snapshot(page, input_root)
    output = output_root / page.name
    output.mkdir(parents=True, exist_ok=True)
    (output / "raw.html").write_text(rendered.html, encoding="utf-8")

    docling_document = _load_docling(rendered, input_root / page.name)
    print("  Docling canonical representation ready", flush=True)
    docling_lean = lean_llm_view(docling_document, source_url=rendered.url)
    unstructured_elements = UnstructuredSourcePartitioner().partition(rendered)
    print("  Unstructured elements ready", flush=True)
    unstructured_lean = lean_unstructured_view(unstructured_elements, source_url=rendered.url)

    docling_canonical_json = _json(docling_document.export_to_dict())
    docling_lean_json = docling_lean.model_dump_json(
        indent=2, exclude_none=True, exclude_defaults=True
    )
    unstructured_canonical_json = _json(canonical_elements(unstructured_elements))
    unstructured_lean_json = unstructured_lean.model_dump_json(
        indent=2, exclude_none=True, exclude_defaults=True
    )

    _write(output / "docling-source.json", docling_canonical_json)
    _write(output / "docling-llm-view.json", docling_lean_json)
    _write(output / "docling-llm-view.md", lean_view_markdown(docling_lean))
    _write(output / "unstructured-elements.json", unstructured_canonical_json)
    _write(output / "unstructured-llm-view.json", unstructured_lean_json)
    _write(
        output / "unstructured-llm-view.md",
        lean_unstructured_markdown(unstructured_lean),
    )
    print("  Canonical and lean outputs written", flush=True)

    hierarchy = {
        _relationship_key(parent, child): {
            "label": f"{parent} → {child}",
            "docling_canonical": docling_native_relationship(docling_document, parent, child),
            "docling_lean": docling_lean_relationship(docling_lean, parent, child),
            "unstructured_canonical": unstructured_native_relationship(
                unstructured_elements, parent, child
            ),
            "unstructured_lean": unstructured_lean_relationship(unstructured_lean, parent, child),
        }
        for parent, child in page.relationships
    }
    comparison = {
        "site": page.name,
        "label": page.label,
        "source_url": rendered.url,
        "source_sha256": rendered.content_sha256,
        "sizes": {
            "raw_html_chars": len(rendered.html),
            "docling_canonical_chars": len(docling_canonical_json),
            "docling_lean_chars": len(docling_lean_json),
            "unstructured_canonical_chars": len(unstructured_canonical_json),
            "unstructured_lean_chars": len(unstructured_lean_json),
            "docling_lean_reduction_percent": _reduction(
                len(docling_canonical_json), len(docling_lean_json)
            ),
            "unstructured_lean_reduction_percent": _reduction(
                len(unstructured_canonical_json), len(unstructured_lean_json)
            ),
        },
        "hierarchy": hierarchy,
        "tables": table_metrics(rendered.html, docling_document, unstructured_elements),
        "noise": {
            "docling": docling_noise(docling_document),
            "unstructured": unstructured_noise(unstructured_elements),
        },
        "provenance": {
            "docling": docling_provenance(docling_document),
            "unstructured": unstructured_provenance(unstructured_elements),
        },
    }
    print("  Metrics calculated", flush=True)
    _write(output / "comparison.json", _json(comparison))
    _print_summary(comparison)
    return comparison


def docling_native_relationship(
    document: DoclingDocument, parent_text: str, child_text: str
) -> bool:
    """Check an ancestor relationship in Docling's native reference graph."""

    items = [item for item, _ in document.iterate_items(with_groups=True)]
    by_ref = {item.self_ref: item for item in items}
    parent_refs = {
        item.self_ref for item in items if _contains(_docling_item_text(item), parent_text)
    }
    for child in items:
        if not _contains(_docling_item_text(child), child_text):
            continue
        parent_ref = getattr(getattr(child, "parent", None), "cref", None)
        visited: set[str] = set()
        while parent_ref and parent_ref in by_ref and parent_ref not in visited:
            if parent_ref in parent_refs:
                return True
            visited.add(parent_ref)
            ancestor = by_ref[parent_ref]
            parent_ref = getattr(getattr(ancestor, "parent", None), "cref", None)
    return False


def docling_lean_relationship(view: LeanSourceView, parent_text: str, child_text: str) -> bool:
    """Check hierarchy after the experimental Docling lean projection."""

    for node in _walk_docling(view.items):
        if _contains(_docling_lean_text(node), parent_text) and any(
            _contains(_docling_lean_text(child), child_text)
            for child in _walk_docling(node.children)
        ):
            return True
    return False


def unstructured_native_relationship(
    elements: list[Element], parent_text: str, child_text: str
) -> bool:
    """Check an ancestor relationship using native Unstructured parent IDs."""

    by_id = {element.id: element for element in elements}
    parent_ids = {element.id for element in elements if _contains(str(element), parent_text)}
    return any(
        _unstructured_has_parent(element, child_text, parent_ids, by_id) for element in elements
    )


def unstructured_lean_relationship(
    view: UnstructuredLeanView, parent_text: str, child_text: str
) -> bool:
    """Check hierarchy after metadata reduction in the lean projection."""

    by_id = {element.source_element_id: element for element in view.elements}
    parent_ids = {
        element.source_element_id
        for element in view.elements
        if _contains(_unstructured_lean_text(element), parent_text)
    }
    for element in view.elements:
        if not _contains(_unstructured_lean_text(element), child_text):
            continue
        parent_id = element.parent_id
        visited: set[str] = set()
        while parent_id and parent_id in by_id and parent_id not in visited:
            if parent_id in parent_ids:
                return True
            visited.add(parent_id)
            parent_id = by_id[parent_id].parent_id
    return False


def table_metrics(
    html: str,
    document: DoclingDocument,
    elements: list[Element],
) -> dict[str, Any]:
    """Measure whether source tables remain structurally recoverable."""

    source = BeautifulSoup(html, "html.parser")
    source_tables = source.find_all("table")
    source_spans = sum(
        1
        for table in source_tables
        for cell in table.find_all(["th", "td"])
        if cell.has_attr("rowspan") or cell.has_attr("colspan")
    )
    docling_cells = [cell for table in document.tables for cell in table.data.table_cells]
    unstructured_tables = [element for element in elements if element.category == "Table"]
    unstructured_html = [
        element.metadata.text_as_html
        for element in unstructured_tables
        if element.metadata.text_as_html
    ]
    parsed_unstructured = [
        BeautifulSoup(html_text, "html.parser") for html_text in unstructured_html
    ]
    return {
        "source_html_tables": len(source_tables),
        "source_spanned_cells": source_spans,
        "docling_tables": len(document.tables),
        "docling_header_cells": sum(
            1 for cell in docling_cells if cell.column_header or cell.row_header
        ),
        "docling_spanned_cells": sum(
            1 for cell in docling_cells if cell.row_span > 1 or cell.col_span > 1
        ),
        "unstructured_tables": len(unstructured_tables),
        "unstructured_tables_with_html": len(unstructured_html),
        "unstructured_html_header_cells": sum(
            len(table.find_all("th")) for table in parsed_unstructured
        ),
        "unstructured_html_spanned_cells": sum(
            1
            for table in parsed_unstructured
            for cell in table.find_all(["th", "td"])
            if cell.has_attr("rowspan") or cell.has_attr("colspan")
        ),
    }


def docling_noise(document: DoclingDocument) -> dict[str, int]:
    """Return library-neutral signals useful for comparing webpage noise."""

    items = list(document.iterate_items())
    texts = [_docling_item_text(item) for item, _ in items]
    texts = [text for text in texts if text]
    return {
        "elements": len(texts),
        "text_chars": sum(len(text) for text in texts),
        "duplicate_elements": _duplicate_count(texts),
        "linked_elements": sum(1 for item, _ in items if getattr(item, "hyperlink", None)),
    }


def unstructured_noise(elements: list[Element]) -> dict[str, int]:
    """Return the same approximate noise signals for Unstructured output."""

    texts = [str(element) for element in elements if str(element)]
    return {
        "elements": len(texts),
        "text_chars": sum(len(text) for text in texts),
        "duplicate_elements": _duplicate_count(texts),
        "linked_elements": sum(1 for element in elements if element.metadata.link_urls),
    }


def docling_provenance(document: DoclingDocument) -> dict[str, bool]:
    items = [item for item, _ in document.iterate_items()]
    provenance = [prov for item in items for prov in (getattr(item, "prov", None) or [])]
    return {
        "source_url": bool(document.origin and document.origin.uri),
        "stable_item_id": all(bool(item.self_ref) for item in items),
        "parent_relationship": any(getattr(item, "parent", None) for item in items),
        "text_quote": any(bool(_docling_item_text(item)) for item in items),
        "dom_selector": False,
        "xpath": False,
        "character_offsets": any(bool(prov.charspan) for prov in provenance),
        "coordinates": any(bool(prov.bbox) for prov in provenance),
    }


def unstructured_provenance(elements: list[Element]) -> dict[str, bool]:
    metadata = [element.metadata.to_dict() for element in elements]
    return {
        "source_url": bool(elements) and all(bool(item.get("url")) for item in metadata),
        "stable_item_id": all(bool(element.id) for element in elements),
        "parent_relationship": any(bool(item.get("parent_id")) for item in metadata),
        "text_quote": any(bool(str(element)) for element in elements),
        "dom_selector": any(bool(item.get("css_selector")) for item in metadata),
        "xpath": any(bool(item.get("xpath")) for item in metadata),
        "character_offsets": any(bool(item.get("character_offsets")) for item in metadata),
        "coordinates": any(bool(item.get("coordinates")) for item in metadata),
    }


async def _load_snapshot(page: BenchmarkPage, input_root: Path) -> RenderedPage:
    site = input_root / page.name
    raw_path = site / "raw.html"
    metadata_path = site / "raw-source.json"
    if raw_path.exists():
        metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
        acquired_at = metadata.get("acquired_at")
        return RenderedPage(
            url=str(metadata.get("source_url") or page.url),
            html=raw_path.read_text(encoding="utf-8"),
            acquired_at=datetime.fromisoformat(acquired_at)
            if acquired_at
            else datetime.now().astimezone(),
        )

    rendered = await Crawl4AIPageLoader().load(page.url)
    site.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(rendered.html, encoding="utf-8")
    _write(
        metadata_path,
        _json(
            {
                "source_url": rendered.url,
                "acquired_at": rendered.acquired_at.isoformat(),
                "sha256": rendered.content_sha256,
            }
        ),
    )
    return rendered


def _load_docling(rendered: RenderedPage, site: Path) -> DoclingDocument:
    """Reuse the saved Docling result, or normalize the shared snapshot once."""

    canonical_path = site / "docling-source.json"
    if canonical_path.exists():
        return DoclingDocument.model_validate_json(canonical_path.read_text(encoding="utf-8"))
    return DoclingSourceNormalizer().normalize(rendered)


def _unstructured_has_parent(
    element: Element,
    child_text: str,
    parent_ids: set[str],
    by_id: dict[str, Element],
) -> bool:
    if not _contains(str(element), child_text):
        return False
    parent_id = element.metadata.parent_id
    visited: set[str] = set()
    while parent_id and parent_id in by_id and parent_id not in visited:
        if parent_id in parent_ids:
            return True
        visited.add(parent_id)
        parent_id = by_id[parent_id].metadata.parent_id
    return False


def _docling_item_text(item: NodeItem) -> str:
    text = getattr(item, "text", None)
    if isinstance(text, str):
        return text
    data = getattr(item, "data", None)
    grid = getattr(data, "grid", None) or []
    return " ".join(cell.text for row in grid for cell in row)


def _docling_lean_text(node: LeanSourceNode) -> str:
    return " ".join(
        part
        for part in (
            node.text,
            " ".join(cell for row in (node.rows or []) for cell in row),
        )
        if part
    )


def _unstructured_lean_text(element: UnstructuredLeanElement) -> str:
    return " ".join(
        (
            element.text,
            " ".join(cell for row in (element.table_rows or []) for cell in row),
        )
    )


def _walk_docling(nodes: list[LeanSourceNode]) -> list[LeanSourceNode]:
    return [node for item in nodes for node in [item, *_walk_docling(item.children)]]


def _contains(value: str, query: str) -> bool:
    return _comparison_key(query) in _comparison_key(value)


def _comparison_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _relationship_key(parent: str, child: str) -> str:
    return "_".join(filter(None, re.split(r"[^a-z0-9]+", f"{parent}_{child}".casefold())))


def _duplicate_count(texts: list[str]) -> int:
    counts = Counter(_comparison_key(text) for text in texts)
    return sum(count - 1 for key, count in counts.items() if key)


def _reduction(canonical: int, lean: int) -> float:
    return round(100 * (1 - lean / max(canonical, 1)), 1)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _write(path: Path, content: str) -> None:
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _print_summary(comparison: dict[str, Any]) -> None:
    print(f"\nSource: {comparison['label']}")
    sizes = comparison["sizes"]
    print(
        "Characters: "
        f"raw={sizes['raw_html_chars']:,}; "
        f"Docling={sizes['docling_canonical_chars']:,}/{sizes['docling_lean_chars']:,}; "
        "Unstructured="
        f"{sizes['unstructured_canonical_chars']:,}/{sizes['unstructured_lean_chars']:,}"
    )
    tables = comparison["tables"]
    print(
        f"Tables: source={tables['source_html_tables']}; "
        f"Docling={tables['docling_tables']}; "
        f"Unstructured={tables['unstructured_tables']}"
    )
    for result in comparison["hierarchy"].values():
        marks = " ".join(
            "✓" if result[key] else "✗"
            for key in (
                "docling_canonical",
                "docling_lean",
                "unstructured_canonical",
                "unstructured_lean",
            )
        )
        print(
            f"Hierarchy [Docling native/lean, Unstructured native/lean] {marks} {result['label']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--site",
        action="append",
        choices=[page.name for page in BENCHMARK_PAGES],
        help="Compare only the selected site; repeat for multiple sites.",
    )
    parser.add_argument("--input", type=Path, default=Path("artifacts/docling"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/source-comparison"))
    args = parser.parse_args()
    selected = [page for page in BENCHMARK_PAGES if not args.site or page.name in args.site]
    for page in selected:
        asyncio.run(compare(page, args.input, args.output))


if __name__ == "__main__":
    main()
