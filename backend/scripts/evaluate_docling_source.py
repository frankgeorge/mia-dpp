"""Evaluate Docling as a generic normalization layer for rendered product pages."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path

from mia_dpp.experiments.docling_source import (
    DoclingSourceNormalizer,
    LeanSourceNode,
    LeanSourceView,
    lean_llm_view,
    lean_view_markdown,
)
from mia_dpp.integrations.crawl4ai import Crawl4AIPageLoader


@dataclass(frozen=True)
class EvaluationPage:
    name: str
    label: str
    url: str
    relationships: tuple[tuple[str, str], ...] = ()


PAGES = (
    EvaluationPage(
        name="afriso",
        label="AFRISO TankControl 25",
        url=(
            "https://www.afriso.com/products/domestic-technology/"
            "level-indicators-and-level-controllers/tankcontrol-20-25/"
            "52161-fuellstandmessgeraet-tankcontrol-25"
        ),
        relationships=(
            ("Operating temperature range", "Medium"),
            ("Operating temperature range", "Ambient"),
            ("Submersible probe", "IP68"),
            ("Housing", "IP54"),
        ),
    ),
    EvaluationPage(
        name="apple-macbook-air",
        label="Apple MacBook Air specifications",
        url="https://www.apple.com/macbook-air/specs/",
    ),
    EvaluationPage(
        name="raspberry-pi-5",
        label="Raspberry Pi 5",
        url="https://www.raspberrypi.com/products/raspberry-pi-5/",
    ),
    EvaluationPage(
        name="framework-laptop-13",
        label="Framework Laptop 13",
        url="https://frame.work/products/laptop13-diy-intel-ultra-1",
    ),
    EvaluationPage(
        name="cisco-catalyst-9200",
        label="Cisco Catalyst 9200 Series data sheet",
        url=(
            "https://www.cisco.com/c/en/us/products/collateral/switches/"
            "catalyst-9200-series-switches/nb-06-cat9200-ser-data-sheet-cte-en.html"
        ),
    ),
)


async def evaluate(page: EvaluationPage, output_root: Path) -> None:
    output = output_root / page.name
    output.mkdir(parents=True, exist_ok=True)

    rendered = await Crawl4AIPageLoader().load(page.url)
    (output / "raw.html").write_text(rendered.html, encoding="utf-8")
    _write_json(
        output / "raw-source.json",
        {
            "source_url": rendered.url,
            "acquired_at": rendered.acquired_at.isoformat(),
            "sha256": rendered.content_sha256,
        },
    )

    document = await asyncio.to_thread(DoclingSourceNormalizer().normalize, rendered)
    canonical = document.export_to_dict()
    canonical_json = json.dumps(canonical, ensure_ascii=False, indent=2)
    (output / "docling-source.json").write_text(canonical_json + "\n", encoding="utf-8")
    (output / "docling-source.md").write_text(document.export_to_markdown(), encoding="utf-8")

    lean = lean_llm_view(document, source_url=rendered.url)
    lean_json = lean.model_dump_json(indent=2, exclude_none=True, exclude_defaults=True)
    (output / "mia-llm-view.json").write_text(lean_json + "\n", encoding="utf-8")
    (output / "mia-llm-view.md").write_text(lean_view_markdown(lean), encoding="utf-8")

    all_items = list(document.iterate_items(with_groups=True))
    groups = sum(1 for item, _ in all_items if item.self_ref.startswith("#/groups/"))
    tables = sum(1 for item, _ in all_items if item.self_ref.startswith("#/tables/"))
    sections = sum(
        1
        for item, _ in all_items
        if getattr(getattr(item, "label", None), "value", None) in {"title", "section_header"}
    )
    provenance = [prov for item, _ in all_items for prov in (getattr(item, "prov", None) or [])]

    print(f"\nSource: {page.label}")
    print(f"URL: {rendered.url}")
    print(f"Docling document items: {len(all_items)}")
    print(f"Groups/sections/tables found: {groups}/{sections}/{tables}")
    print("\nHierarchy checks:")
    if page.relationships:
        for parent, child in page.relationships:
            mark = "✓" if _contains_relationship(lean, parent, child) else "✗"
            print(f"{mark} {parent} → {child}")
    else:
        print("(no site-specific expectations; inspect the generic tree output)")
    print("\nProvenance:")
    print(f"source URL: {'yes' if document.origin and document.origin.uri else 'no'}")
    print(f"item page/source refs: {'yes' if provenance else 'no'}")
    print(f"bounding/layout data: {'yes' if any(p.bbox for p in provenance) else 'no'}")
    print("exact HTML/DOM locator: no")
    reduction = 100 * (1 - len(lean_json) / max(len(canonical_json), 1))
    print("\nLean view size:")
    print(f"canonical JSON: {len(canonical_json):,} chars")
    print(f"LLM JSON: {len(lean_json):,} chars")
    print(f"reduction: {reduction:.1f}%")


def _contains_relationship(view: LeanSourceView, parent: str, child: str) -> bool:
    parent_key = _comparison_key(parent)
    child_key = _comparison_key(child)
    for node in _walk(view.items):
        if parent_key not in _comparison_key(_node_text(node)):
            continue
        descendants = _walk(node.children)
        if any(child_key in _comparison_key(_node_text(item)) for item in descendants):
            return True
    return False


def _walk(items: list[LeanSourceNode]) -> list[LeanSourceNode]:
    return [node for item in items for node in [item, *_walk(item.children)]]


def _node_text(node: LeanSourceNode) -> str:
    rows = " ".join(cell for row in (node.rows or []) for cell in row)
    return " ".join(part for part in (node.text, rows) if part)


def _comparison_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--site",
        action="append",
        choices=[page.name for page in PAGES],
        help="Evaluate only the selected site; repeat for multiple sites.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/docling"),
        help="Directory for generated experiment artifacts.",
    )
    args = parser.parse_args()
    selected = [page for page in PAGES if not args.site or page.name in args.site]
    for page in selected:
        asyncio.run(evaluate(page, args.output))


if __name__ == "__main__":
    main()
