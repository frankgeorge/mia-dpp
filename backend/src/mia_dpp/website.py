"""Crawl4AI-backed product-page ingestion using the existing mapping logic."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from mia_dpp.chat import CONFIDENCE_THRESHOLD, nameplate_catalog
from mia_dpp.errors import ExtractionError
from mia_dpp.extraction import Crawl4AIPageLoader, PageLoader, RenderedPage
from mia_dpp.idta import demo_propose
from mia_dpp.models import (
    EvidenceRecord,
    EvidenceStatus,
    MappingProposal,
    MappingStatus,
    ProposedFieldMapping,
    SourceLocation,
    WebsiteIngestRequest,
    WebsiteIngestResponse,
)
from mia_dpp.templates import OfficialTemplateRepository
from mia_dpp.url_policy import ProductUrlPolicy

_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_PREFERRED_SIGNAL_LABELS = {
    "manufacturer.name": frozenset({"manufacturer"}),
    "product.designation": frozenset({"model", "designation"}),
    "product.serial_number": frozenset({"serial number"}),
    "product.order_code": frozenset({"order code"}),
    "product.year_of_construction": frozenset({"year of construction"}),
    "product.country_of_origin": frozenset({"made in"}),
}


@dataclass(frozen=True, slots=True)
class PageSignal:
    """One labelled value used to give the existing parser better page context."""

    label: str
    value: str
    method: str
    location: SourceLocation


class ProductPageText:
    """Turn common JSON-LD and specification markup into labelled plain text."""

    def extract(self, page: RenderedPage) -> tuple[str, tuple[PageSignal, ...], str]:
        soup = BeautifulSoup(page.html, "html.parser")
        signals = [*self._json_ld_signals(soup), *self._html_label_signals(soup)]
        heading = soup.find("h1")
        product_name = self._first_value(signals, "product name", "model")
        if not product_name and heading is not None:
            product_name = self._text(heading.get_text(" ", strip=True))
            if product_name:
                signals.insert(
                    0,
                    PageSignal(
                        label="designation",
                        value=product_name,
                        method="css",
                        location=SourceLocation(selector="h1", excerpt=product_name[:240]),
                    ),
                )
        for node in soup(["script", "style", "noscript"]):
            node.decompose()
        visible = self._text(soup.get_text(" ", strip=True))
        labelled = "\n".join(f"{item.label}: {item.value}" for item in signals)
        combined = "\n".join(part for part in (labelled, visible) if part)
        fallback = urlsplit(page.url).hostname or "Website product"
        return combined, tuple(signals), (product_name or fallback)[:120]

    @classmethod
    def _json_ld_signals(cls, soup: BeautifulSoup) -> list[PageSignal]:
        signals: list[PageSignal] = []
        for script_index, script in enumerate(soup.select('script[type="application/ld+json"]')):
            raw = script.string if script.string is not None else script.get_text()
            try:
                document = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            selector = f"script[type='application/ld+json'] (match {script_index + 1})"
            for entity, pointer in cls._entities(document):
                if not cls._is_product(entity):
                    continue
                cls._append_json_fields(signals, entity, pointer, selector)
        return cls._deduplicate(signals)

    @classmethod
    def _append_json_fields(
        cls,
        signals: list[PageSignal],
        entity: dict[str, Any],
        pointer: str,
        selector: str,
    ) -> None:
        def append(label: str, value: Any, field_pointer: str) -> None:
            text = cls._named_value(value)
            if text:
                signals.append(
                    PageSignal(
                        label=label,
                        value=text,
                        method="json_ld",
                        location=SourceLocation(
                            selector=selector,
                            json_pointer=f"{pointer}/{field_pointer}",
                            excerpt=text[:240],
                        ),
                    )
                )

        append("manufacturer", entity.get("manufacturer") or entity.get("brand"), "manufacturer")
        model = entity.get("model")
        name = entity.get("name")
        append("model", model, "model")
        append("product name", name, "name")
        if not cls._named_value(model):
            append("designation", name, "name")
        append("serial number", entity.get("serialNumber"), "serialNumber")
        append("order code", entity.get("sku") or entity.get("mpn"), "sku")
        production_date = cls._named_value(entity.get("productionDate"))
        if production_date and (year := _YEAR.search(production_date)):
            append("year of construction", year.group(1), "productionDate")
        append("made in", entity.get("countryOfOrigin"), "countryOfOrigin")

        additional = entity.get("additionalProperty")
        properties = [additional] if isinstance(additional, dict) else additional
        if isinstance(properties, list):
            for index, item in enumerate(properties):
                if not isinstance(item, dict):
                    continue
                label = cls._named_value(item.get("name") or item.get("propertyID"))
                value = cls._named_value(item.get("value"))
                if label and value:
                    append(label, value, f"additionalProperty/{index}/value")

    @classmethod
    def _html_label_signals(cls, soup: BeautifulSoup) -> list[PageSignal]:
        signals: list[PageSignal] = []
        for index, term in enumerate(soup.find_all("dt")):
            value = term.find_next_sibling("dd")
            if value is not None:
                cls._append_html_signal(signals, term, value, f"dt:nth-of-type({index + 1})")
        for index, row in enumerate(soup.find_all("tr")):
            cells = row.find_all(["th", "td"], recursive=False)
            if len(cells) >= 2:
                cls._append_html_signal(signals, cells[0], cells[1], f"tr:nth-of-type({index + 1})")
        return cls._deduplicate(signals)

    @classmethod
    def _append_html_signal(
        cls,
        signals: list[PageSignal],
        label_node: Any,
        value_node: Any,
        selector: str,
    ) -> None:
        label = cls._text(label_node.get_text(" ", strip=True))
        value = cls._text(value_node.get_text(" ", strip=True))
        if label and value and len(label) <= 80 and len(value) <= 500:
            signals.append(
                PageSignal(
                    label=label,
                    value=value,
                    method="html_label",
                    location=SourceLocation(selector=selector, excerpt=f"{label}: {value}"[:240]),
                )
            )

    @classmethod
    def _entities(cls, value: Any, pointer: str = "") -> list[tuple[dict[str, Any], str]]:
        if isinstance(value, list):
            return [
                entity
                for index, item in enumerate(value)
                for entity in cls._entities(item, f"{pointer}/{index}")
            ]
        if not isinstance(value, dict):
            return []
        result = [(value, pointer)]
        graph = value.get("@graph")
        if isinstance(graph, list):
            result.extend(
                entity
                for index, item in enumerate(graph)
                for entity in cls._entities(item, f"{pointer}/@graph/{index}")
            )
        return result

    @staticmethod
    def _is_product(entity: dict[str, Any]) -> bool:
        declared = entity.get("@type")
        types = declared if isinstance(declared, list) else [declared]
        return any(
            isinstance(item, str) and item.rstrip("/").rsplit("/", 1)[-1].casefold() == "product"
            for item in types
        )

    @classmethod
    def _named_value(cls, value: Any) -> str:
        if isinstance(value, dict):
            value = value.get("name")
        if isinstance(value, (str, int, float, bool)):
            return cls._text(str(value))
        return ""

    @staticmethod
    def _text(value: str) -> str:
        return " ".join(value.split()).strip()

    @staticmethod
    def _deduplicate(signals: list[PageSignal]) -> list[PageSignal]:
        seen: set[tuple[str, str]] = set()
        result: list[PageSignal] = []
        for signal in signals:
            key = (signal.label.casefold(), signal.value.casefold())
            if key not in seen:
                seen.add(key)
                result.append(signal)
        return result

    @staticmethod
    def _first_value(signals: list[PageSignal], *labels: str) -> str:
        for label in labels:
            value = next(
                (item.value for item in signals if item.label.casefold() == label.casefold()),
                "",
            )
            if value:
                return value
        return ""


class WebsiteIngestionService:
    """Compose Crawl4AI output with the existing deterministic proposal path."""

    def __init__(
        self,
        repository: OfficialTemplateRepository,
        *,
        loader: PageLoader | None = None,
        url_policy: ProductUrlPolicy | None = None,
        text_extractor: ProductPageText | None = None,
    ) -> None:
        self._repository = repository
        self._loader = loader or Crawl4AIPageLoader()
        self._url_policy = url_policy or ProductUrlPolicy()
        self._text_extractor = text_extractor or ProductPageText()

    async def ingest(self, request: WebsiteIngestRequest) -> WebsiteIngestResponse:
        requested_url = await self._url_policy.validate(request.url)
        page = await self._loader.load(requested_url)
        final_url = await self._url_policy.validate(page.url)
        if final_url != page.url:
            page = RenderedPage(url=final_url, html=page.html, acquired_at=page.acquired_at)

        source_text, signals, product_name = self._text_extractor.extract(page)
        if not source_text:
            raise ExtractionError("the product page contained no usable text")
        history = {
            (entry.source_field.casefold(), entry.target_element): max(entry.corrections, 1)
            for entry in request.graph
        }
        draft = demo_propose(
            source_text,
            self._repository,
            history=history,
            allow_unlabelled_year=False,
        )
        if not draft.mappings:
            raise ExtractionError(
                "the page was fetched, but no supported product fields could be identified"
            )

        evidence, id_map = self._website_evidence(page, draft.evidence, signals)
        mappings = tuple(
            ProposedFieldMapping(
                **mapping.model_copy(
                    update={"evidence_id": id_map[mapping.evidence_id]}
                ).model_dump(),
                status=(
                    MappingStatus.AUTO
                    if mapping.confidence >= CONFIDENCE_THRESHOLD
                    else MappingStatus.REVIEW
                ),
            )
            for mapping in draft.mappings
        )
        return WebsiteIngestResponse(
            reply=(
                f"Crawl4AI fetched {page.url}. MIA retained {len(evidence)} product facts "
                "with page provenance and mapped them for your review."
            ),
            source_url=page.url,
            proposal=MappingProposal(product_name=product_name, mappings=mappings),
            evidence=evidence,
            nameplate_elements=nameplate_catalog(self._repository),
        )

    @staticmethod
    def _website_evidence(
        page: RenderedPage,
        extracted: tuple[EvidenceRecord, ...],
        signals: tuple[PageSignal, ...],
    ) -> tuple[tuple[EvidenceRecord, ...], dict[str, str]]:
        result: list[EvidenceRecord] = []
        id_map: dict[str, str] = {}
        for record in extracted:
            signal = WebsiteIngestionService._matching_signal(record, signals)
            location = (
                signal.location
                if signal is not None
                else SourceLocation(selector="body", excerpt=record.source_location.excerpt)
            )
            identity = "\0".join(
                (
                    page.content_sha256,
                    record.predicate,
                    str(record.value),
                    location.selector or "",
                    location.json_pointer or "",
                )
            )
            evidence_id = f"ev-web-{hashlib.sha256(identity.encode()).hexdigest()[:24]}"
            id_map[record.id] = evidence_id
            result.append(
                record.model_copy(
                    update={
                        "id": evidence_id,
                        "source_uri": page.url,
                        "source_content_sha256": page.content_sha256,
                        "source_location": location,
                        "extraction_method": (
                            signal.method if signal is not None else "crawl4ai_visible_text"
                        ),
                        "extractor_name": "mia-crawl4ai-product-page",
                        "extractor_version": "1",
                        "status": EvidenceStatus.OBSERVED,
                        "acquired_at": page.acquired_at,
                    }
                )
            )
        return tuple(result), id_map

    @staticmethod
    def _matching_signal(
        record: EvidenceRecord,
        signals: tuple[PageSignal, ...],
    ) -> PageSignal | None:
        same_value = tuple(
            item for item in signals if item.value.casefold() == str(record.value).casefold()
        )
        preferred_labels = _PREFERRED_SIGNAL_LABELS.get(record.predicate)
        if preferred_labels is None:
            return same_value[0] if same_value else None
        return next(
            (item for item in same_value if item.label.casefold() in preferred_labels),
            None,
        )
