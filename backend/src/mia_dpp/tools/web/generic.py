"""Generic extraction from unfamiliar product pages using common HTML structures."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from typing import Any

from bs4 import BeautifulSoup

from mia_dpp.domain.evidence import EvidenceRecord, EvidenceStatus, SourceLocation
from mia_dpp.tools.web.models import RenderedPage

EXTRACTOR_NAME = "mia-website-fact-extractor"
EXTRACTOR_VERSION = "2"
_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_JSON_LABELS = {
    "name": "Product name",
    "sku": "SKU",
    "mpn": "MPN",
    "serialNumber": "Serial number",
    "productionDate": "Production date",
    "countryOfOrigin": "Country of origin",
}
_STRUCTURAL_JSON_KEYS = frozenset({"@context", "@type", "additionalProperty"})
_REFERENCE_JSON_KEYS = frozenset({"url", "image", "logo", "sameAs"})


class WebsiteFactExtractor:
    """Retain useful labelled facts found in common product-page structures."""

    def extract(self, source: RenderedPage) -> tuple[tuple[EvidenceRecord, ...], str]:
        """Extract normalized, provenance-rich evidence directly from one page."""

        soup = BeautifulSoup(source.html, "html.parser")
        facts: list[EvidenceRecord] = []

        for script_index, script in enumerate(soup.select('script[type="application/ld+json"]')):
            raw = script.string if script.string is not None else script.get_text()
            try:
                document = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            selector = f"script[type='application/ld+json'] (match {script_index + 1})"
            for entity, pointer in self._product_entities(document):
                self._append_json_product(facts, source, entity, pointer, selector)

        heading = soup.find("h1")
        if heading is not None:
            value = self._text(heading.get_text(" ", strip=True))
            self._append(
                facts,
                source,
                label="Product name",
                value=value,
                method="css",
                location=SourceLocation(selector="h1", excerpt=value[:240]),
            )

        title = soup.find("title")
        if title is not None:
            value = self._text(title.get_text(" ", strip=True))
            self._append(
                facts,
                source,
                label="Page title",
                value=value,
                method="html_metadata",
                location=SourceLocation(selector="title", excerpt=value[:240]),
            )

        self._append(
            facts,
            source,
            label="Product page URL",
            value=source.url,
            method="source_metadata",
            location=SourceLocation(excerpt=source.url[:240]),
        )

        self._extract_grouped_properties(facts, source, soup)
        for index, term in enumerate(soup.find_all("dt")):
            classes = set(term.get("class") or ())

            if classes & {"groupingProperty", "groupedProperty"}:
                continue

            value_node = term.find_next_sibling("dd")

            if value_node is not None:
                self._append_html_pair(
                    facts,
                    source,
                    term,
                    value_node,
                    SourceLocation(selector=f"dt:nth-of-type({index + 1})"),
                )

        for table_index, table in enumerate(soup.find_all("table")):
            caption = table.find("caption")
            table_name = (
                self._text(caption.get_text(" ", strip=True))
                if caption is not None
                else f"table {table_index + 1}"
            )
            for row_index, row in enumerate(table.find_all("tr")):
                cells = row.find_all(["th", "td"], recursive=False)
                if len(cells) >= 2:
                    self._append_html_pair(
                        facts,
                        source,
                        cells[0],
                        cells[1],
                        SourceLocation(
                            selector=(
                                f"table:nth-of-type({table_index + 1}) "
                                f"tr:nth-of-type({row_index + 1})"
                            ),
                            table=table_name,
                            cell=f"row {row_index + 1}",
                        ),
                    )

        facts = self._deduplicate(facts)
        product_name = self._first_value(facts, "Product name", "Model", "Page title")
        return tuple(facts), (product_name or source.url)[:120]

    def _extract_grouped_properties(
        self,
        facts: list[EvidenceRecord],
        source: RenderedPage,
        soup: BeautifulSoup,
    ) -> None:
        for group_index, group in enumerate(soup.select("div.group"), 1):
            parent_node = group.select_one(
                ":scope > dl > dt.groupingProperty"
            )

            if parent_node is None:
                continue

            parent = self._text(
                parent_node.get_text(" ", strip=True)
            )

            if not parent:
                continue

            context_path = (parent,)
            child_index = 0

            for dl in group.find_all("dl", recursive=False):
                label_node = dl.find("dt", recursive=False)
                value_node = dl.find("dd", recursive=False)

                if label_node is None or value_node is None:
                    continue

                label_classes = set(label_node.get("class") or ())
                value_classes = set(value_node.get("class") or ())

                if (
                    "groupedProperty" not in label_classes
                    and "groupedProperty" not in value_classes
                ):
                    continue

                label = self._text(
                    label_node.get_text(" ", strip=True)
                )
                value = self._text(
                    value_node.get_text(" ", strip=True)
                )

                # Leave description-only children for the next step.
                if not label or not value:
                    continue

                child_index += 1

                self._append_html_pair(
                    facts,
                    source,
                    label_node,
                    value_node,
                    SourceLocation(
                        selector=(
                            f"div.group:nth-of-type({group_index}) "
                            f"dt.groupedProperty:nth-of-type({child_index})"
                        )
                    ),
                    context_path=context_path,
                    method="html_grouped_label",
                )

    def _append_json_product(
        self,
        facts: list[EvidenceRecord],
        source: RenderedPage,
        entity: dict[str, Any],
        pointer: str,
        selector: str,
    ) -> None:
        for key, raw_value in entity.items():
            if key in _STRUCTURAL_JSON_KEYS or key in _REFERENCE_JSON_KEYS:
                continue
            if key == "offers" or key in {"review", "aggregateRating"}:
                continue
            label = _JSON_LABELS.get(key, self._humanize(key))
            extracted = self._json_values(raw_value)
            for occurrence, (value, unit) in enumerate(extracted):
                suffix = f"/{occurrence}" if len(extracted) > 1 else ""
                location = SourceLocation(
                    selector=selector,
                    json_pointer=f"{pointer}/{self._pointer_token(key)}{suffix}",
                    excerpt=f"{label}: {value}"[:240],
                )
                self._append(
                    facts,
                    source,
                    label=label,
                    value=value,
                    unit=unit,
                    method="json_ld",
                    location=location,
                )

                if key == "productionDate" and (year := _YEAR.search(value)):
                    self._append(
                        facts,
                        source,
                        label="Year of construction",
                        value=year.group(1),
                        method="json_ld_derived",
                        location=location.model_copy(
                            update={"excerpt": f"Derived year {year.group(1)} from {value}"}
                        ),
                    )

        additional = entity.get("additionalProperty")
        properties = [additional] if isinstance(additional, dict) else additional
        if isinstance(properties, list):
            for index, item in enumerate(properties):
                if not isinstance(item, dict):
                    continue
                label = self._scalar(item.get("name") or item.get("propertyID"))
                value = self._scalar(item.get("value"))
                unit = self._scalar(item.get("unitText") or item.get("unitCode")) or None
                if label and value:
                    self._append(
                        facts,
                        source,
                        label=label,
                        value=value,
                        unit=unit,
                        method="json_ld_additional_property",
                        location=SourceLocation(
                            selector=selector,
                            json_pointer=f"{pointer}/additionalProperty/{index}/value",
                            excerpt=f"{label}: {value}"[:240],
                        ),
                    )

    def _append_html_pair(
        self,
        facts: list[EvidenceRecord],
        source: RenderedPage,
        label_node: Any,
        value_node: Any,
        location: SourceLocation,
        *,
        context_path: tuple[str, ...] = (),
        method: str = "html_label",
    ) -> None:
        label = self._text(label_node.get_text(" ", strip=True))
        value = self._text(value_node.get_text(" ", strip=True))
        if not label or not value or len(label) > 120 or len(value) > 2_000:
            return
        self._append(
            facts,
            source,
            label=label,
            value=value,
            method=method,
            location=location.model_copy(update={"excerpt": f"{label}: {value}"[:240]}),
            context_path=context_path,
        )

    @staticmethod
    def _append(
        facts: list[EvidenceRecord],
        source: RenderedPage,
        *,
        label: str,
        value: str,
        method: str,
        location: SourceLocation,
        unit: str | None = None,
        context_path: tuple[str, ...] = (),
    ) -> None:
        label = WebsiteFactExtractor._text(label)
        value = WebsiteFactExtractor._text(value)
        if not label or not value or len(label) > 120 or len(value) > 2_000:
            return

        context_path = tuple(
            WebsiteFactExtractor._text(item)
            for item in context_path
            if WebsiteFactExtractor._text(item)
        )

        context_identity = "\x1f".join(
            item.casefold() for item in context_path
        )
        identity = "\0".join(
            (
                WebsiteFactExtractor._source_id(source),
                context_identity,
                label.casefold(),
                value,
                unit or "",
                location.selector or "",
                location.json_pointer or "",
            )
        )
        evidence_id = f"ev-web-{hashlib.sha256(identity.encode()).hexdigest()[:24]}"
        facts.append(
            EvidenceRecord(
                id=evidence_id,
                predicate=f"source.{WebsiteFactExtractor._slug(label)}",
                source_label=label,
                value=value,
                unit=unit,
                context_path=context_path,
                source_location=location,
                extraction_method=method,
                extractor_name=EXTRACTOR_NAME,
                extractor_version=EXTRACTOR_VERSION,
                status=EvidenceStatus.OBSERVED,
                source_uri=source.url,
                source_content_sha256=source.content_sha256,
                acquired_at=source.acquired_at,
            )
        )

    @classmethod
    def _json_values(cls, value: Any) -> list[tuple[str, str | None]]:
        if isinstance(value, (str, int, float, bool)):
            return [(cls._text(str(value)), None)]
        if isinstance(value, list):
            return [item for entry in value for item in cls._json_values(entry)]
        if not isinstance(value, dict):
            return []
        direct = cls._scalar(value.get("value"))
        if direct:
            unit = cls._scalar(value.get("unitText") or value.get("unitCode")) or None
            return [(direct, unit)]
        named = cls._scalar(value.get("name"))
        return [(named, None)] if named else []

    @classmethod
    def _product_entities(
        cls,
        value: Any,
        pointer: str = "",
    ) -> Iterable[tuple[dict[str, Any], str]]:
        if isinstance(value, list):
            for index, item in enumerate(value):
                yield from cls._product_entities(item, f"{pointer}/{index}")
            return
        if not isinstance(value, dict):
            return
        declared = value.get("@type")
        types = declared if isinstance(declared, list) else [declared]
        if any(
            isinstance(item, str) and item.rstrip("/").rsplit("/", 1)[-1].casefold() == "product"
            for item in types
        ):
            yield value, pointer
        for key, item in value.items():
            if key not in {"@context"} and isinstance(item, (dict, list)):
                yield from cls._product_entities(
                    item,
                    f"{pointer}/{cls._pointer_token(key)}",
                )

    @staticmethod
    def _deduplicate(facts: list[EvidenceRecord]) -> list[EvidenceRecord]:
        seen: set[tuple[tuple[str, ...], str, str, str]] = set()
        result: list[EvidenceRecord] = []

        for fact in facts:
            key = (
                tuple(item.casefold() for item in fact.context_path),
                (fact.source_label or fact.predicate).casefold(),
                str(fact.value).casefold(),
                fact.unit or "",
            )

            if key not in seen:
                seen.add(key)
                result.append(fact)

        return result

    @staticmethod
    def _first_value(facts: list[EvidenceRecord], *labels: str) -> str:
        wanted = [label.casefold() for label in labels]
        for label in wanted:
            for fact in facts:
                if (fact.source_label or fact.predicate).casefold() == label:
                    return str(fact.value)
        return ""

    @staticmethod
    def _humanize(value: str) -> str:
        words = _CAMEL_BOUNDARY.sub(" ", value).replace("_", " ")
        return WebsiteFactExtractor._text(words).capitalize()

    @staticmethod
    def _pointer_token(value: str) -> str:
        return value.replace("~", "~0").replace("/", "~1")

    @staticmethod
    def _scalar(value: Any) -> str:
        if isinstance(value, (str, int, float, bool)):
            return WebsiteFactExtractor._text(str(value))
        return ""

    @staticmethod
    def _text(value: str) -> str:
        return " ".join(value.split()).strip()

    @staticmethod
    def _source_id(source: RenderedPage) -> str:
        return f"source-web-{source.content_sha256[:24]}"

    @staticmethod
    def _slug(label: str) -> str:
        return re.sub(r"[^a-z0-9]+", ".", label.casefold()).strip(".") or "fact"
