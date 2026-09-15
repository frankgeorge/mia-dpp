"""Experimental Docling normalization of Crawl4AI-rendered HTML."""

from __future__ import annotations

from typing import Any

from docling.datamodel.backend_options import HTMLBackendOptions
from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter, HTMLFormatOption
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.items.group import GroupItem
from docling_core.types.doc.items.node import NodeItem
from docling_core.types.doc.items.table.table import TableItem
from pydantic import AnyUrl, BaseModel, ConfigDict, Field

from mia_dpp.tools.web.models import RenderedPage


class LeanSourceNode(BaseModel):
    """One lightweight, hierarchically nested item shown to an LLM."""

    model_config = ConfigDict(extra="forbid")

    source_item_id: str
    kind: str
    text: str | None = None
    rows: list[list[str]] | None = None
    children: list[LeanSourceNode] = Field(default_factory=list)


class LeanSourceView(BaseModel):
    """Compact semantic view derived only from a canonical Docling document."""

    model_config = ConfigDict(extra="forbid")

    source_url: str
    title: str
    items: list[LeanSourceNode]


class DoclingSourceNormalizer:
    """Convert already-rendered HTML into Docling's canonical document model.

    Crawl4AI remains responsible for acquisition and dynamic rendering. This
    experimental adapter passes its HTML to Docling without issuing another
    page request, then records the original URL in the document origin.
    """

    def normalize(self, source: RenderedPage) -> DoclingDocument:
        options = HTMLBackendOptions.model_validate(
            {
                "source_uri": source.url,
                "enable_remote_fetch": False,
                "enable_local_fetch": False,
                "fetch_images": False,
            }
        )
        converter = DocumentConverter(
            allowed_formats=[InputFormat.HTML],
            format_options={InputFormat.HTML: HTMLFormatOption(backend_options=options)},
        )
        result = converter.convert_string(
            source.html,
            format=InputFormat.HTML,
            name="rendered-page.html",
        )
        if result.document.origin is not None:
            result.document.origin = result.document.origin.model_copy(
                update={"uri": AnyUrl(source.url)}
            )
        return result.document


def lean_llm_view(document: DoclingDocument, *, source_url: str) -> LeanSourceView:
    """Project a Docling tree into compact JSON without re-extracting facts."""

    items = [
        node
        for child in document.body.children
        for node in _lean_nodes(child.resolve(document), document)
    ]
    title = next((node.text for node in _walk(items) if node.kind == "title"), None)
    return LeanSourceView(source_url=source_url, title=title or document.name, items=items)


def lean_view_markdown(view: LeanSourceView) -> str:
    """Render the compact JSON tree as a human-readable debugging view."""

    lines = [f"# {view.title}", "", f"Source: {view.source_url}", ""]
    for item in view.items:
        _append_markdown(lines, item, depth=0)
    return "\n".join(lines).rstrip() + "\n"


def _lean_nodes(
    item: NodeItem,
    document: DoclingDocument,
) -> list[LeanSourceNode]:
    children = [
        node for child in item.children for node in _lean_nodes(child.resolve(document), document)
    ]
    if isinstance(item, GroupItem):
        return children

    label = getattr(item, "label", None)
    kind = getattr(label, "value", None) or type(item).__name__.removesuffix("Item").lower()
    text = _clean_text(getattr(item, "text", None))
    rows = _table_rows(item) if isinstance(item, TableItem) else None
    if text is None and not rows and not children:
        return []
    return [
        LeanSourceNode(
            source_item_id=item.self_ref,
            kind=kind,
            text=text,
            rows=rows,
            children=children,
        )
    ]


def _table_rows(table: TableItem) -> list[list[str]]:
    return [[_clean_text(cell.text) or "" for cell in row] for row in table.data.grid]


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _walk(items: list[LeanSourceNode]) -> list[LeanSourceNode]:
    return [node for item in items for node in [item, *_walk(item.children)]]


def _append_markdown(lines: list[str], item: LeanSourceNode, *, depth: int) -> None:
    indent = "  " * depth
    if item.rows:
        for row in item.rows:
            lines.append(f"{indent}- " + " | ".join(row))
    elif item.text:
        lines.append(f"{indent}- {item.text} [{item.source_item_id}]")
    for child in item.children:
        _append_markdown(lines, child, depth=depth + 1)
