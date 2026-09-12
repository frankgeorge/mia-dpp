"""Generic extraction from unfamiliar product pages using common HTML structures."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from typing import Any

from bs4 import BeautifulSoup

from mia_dpp.domain.evidence import SourceLocation
from mia_dpp.tools.web.models import CandidateFact, RawSourceArtifact

EXTRACTOR_VERSION = "1"
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

    def extract(self, source: RawSourceArtifact) -> tuple[tuple[CandidateFact, ...], str]:
        soup = BeautifulSoup(source.content, "html.parser")
        facts: list[CandidateFact] = []

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
            value=source.source_uri,
            method="source_metadata",
            location=SourceLocation(excerpt=source.source_uri[:240]),
        )

        for index, term in enumerate(soup.find_all("dt")):
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
        return tuple(facts), (product_name or source.source_uri)[:120]

    def _append_json_product(
        self,
        facts: list[CandidateFact],
        source: RawSourceArtifact,
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
        facts: list[CandidateFact],
        source: RawSourceArtifact,
        label_node: Any,
        value_node: Any,
        location: SourceLocation,
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
            method="html_label",
            location=location.model_copy(update={"excerpt": f"{label}: {value}"[:240]}),
        )

    @staticmethod
    def _append(
        facts: list[CandidateFact],
        source: RawSourceArtifact,
        *,
        label: str,
        value: str,
        method: str,
        location: SourceLocation,
        unit: str | None = None,
    ) -> None:
        label = WebsiteFactExtractor._text(label)
        value = WebsiteFactExtractor._text(value)
        if not label or not value or len(label) > 120 or len(value) > 2_000:
            return
        identity = "\0".join(
            (
                source.id,
                label.casefold(),
                value,
                unit or "",
                location.selector or "",
                location.json_pointer or "",
            )
        )
        fact_id = f"fact-web-{hashlib.sha256(identity.encode()).hexdigest()[:24]}"
        facts.append(
            CandidateFact(
                id=fact_id,
                source_artifact_id=source.id,
                label=label,
                value=value,
                unit=unit,
                source_location=location,
                extraction_method=method,
                raw_context=location.excerpt,
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
    def _deduplicate(facts: list[CandidateFact]) -> list[CandidateFact]:
        seen: set[tuple[str, str, str]] = set()
        result: list[CandidateFact] = []
        for fact in facts:
            key = (fact.label.casefold(), str(fact.value).casefold(), fact.unit or "")
            if key not in seen:
                seen.add(key)
                result.append(fact)
        return result

    @staticmethod
    def _first_value(facts: list[CandidateFact], *labels: str) -> str:
        wanted = [label.casefold() for label in labels]
        for label in wanted:
            for fact in facts:
                if fact.label.casefold() == label:
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
