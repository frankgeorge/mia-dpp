"""Experimental Unstructured partitioning of Crawl4AI-rendered HTML."""

from __future__ import annotations

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict
from unstructured.documents.elements import Element
from unstructured.partition.html import partition_html

from mia_dpp.tools.web.models import RenderedPage


class UnstructuredLeanElement(BaseModel):
    """One compact native element reference intended for an LLM."""

    model_config = ConfigDict(extra="forbid")

    source_element_id: str
    kind: str
    text: str
    parent_id: str | None = None
    category_depth: int | None = None
    table_rows: list[list[str]] | None = None


class UnstructuredLeanView(BaseModel):
    """Lean deterministic projection of native Unstructured elements."""

    model_config = ConfigDict(extra="forbid")

    source_url: str
    elements: list[UnstructuredLeanElement]


class UnstructuredSourcePartitioner:
    """Partition rendered HTML without performing a second web request."""

    def partition(self, source: RenderedPage) -> list[Element]:
        elements = partition_html(
            text=source.html,
            html_parser_version="v1",
            skip_headers_and_footers=True,
            languages=[""],
        )
        for element in elements:
            element.metadata.url = source.url
            element.metadata.filename = "rendered-page.html"
        return elements


def canonical_elements(elements: list[Element]) -> list[dict[str, object]]:
    """Serialize elements with all native metadata retained."""

    return [element.to_dict() for element in elements]


def lean_unstructured_view(elements: list[Element], *, source_url: str) -> UnstructuredLeanView:
    """Remove heavy metadata while preserving native IDs and parent links."""

    lean = []
    for element in elements:
        text = " ".join(str(element).split())
        metadata = element.metadata
        lean.append(
            UnstructuredLeanElement(
                source_element_id=element.id,
                kind=element.category,
                text=text,
                parent_id=metadata.parent_id,
                category_depth=metadata.category_depth,
                table_rows=_table_rows(metadata.text_as_html),
            )
        )
    return UnstructuredLeanView(source_url=source_url, elements=lean)


def lean_unstructured_markdown(view: UnstructuredLeanView) -> str:
    """Render the lean element sequence for human inspection."""

    by_id = {element.source_element_id: element for element in view.elements}
    lines = ["# Unstructured view", "", f"Source: {view.source_url}", ""]
    for element in view.elements:
        depth = _parent_depth(element, by_id)
        prefix = "  " * depth + "- "
        if element.table_rows:
            lines.append(f"{prefix}[{element.kind}] [{element.source_element_id}]")
            lines.extend(f"{'  ' * (depth + 1)}- " + " | ".join(row) for row in element.table_rows)
        else:
            lines.append(f"{prefix}[{element.kind}] {element.text} [{element.source_element_id}]")
    return "\n".join(lines).rstrip() + "\n"


def _table_rows(text_as_html: str | None) -> list[list[str]] | None:
    if not text_as_html:
        return None
    soup = BeautifulSoup(text_as_html, "html.parser")
    rows = [
        [" ".join(cell.get_text(" ", strip=True).split()) for cell in row.find_all(["th", "td"])]
        for row in soup.find_all("tr")
    ]
    return [row for row in rows if row] or None


def _parent_depth(
    element: UnstructuredLeanElement,
    by_id: dict[str, UnstructuredLeanElement],
) -> int:
    depth = 0
    parent_id = element.parent_id
    visited: set[str] = set()
    while parent_id and parent_id in by_id and parent_id not in visited:
        visited.add(parent_id)
        depth += 1
        parent_id = by_id[parent_id].parent_id
    return depth
