"""Deterministic extraction of provenance-rich facts from rendered HTML.

The domain-facing extractor consumes only :class:`RenderedPage` and MIA's own
Pydantic contracts.  Browser implementations such as Crawl4AI stay behind a
small loader boundary and are imported only when explicitly used.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlsplit

from mia_dpp.errors import ExtractionError
from mia_dpp.models import (
    EvidenceRecord,
    EvidenceStatus,
    ExtractionRule,
    ExtractionSource,
    SiteAdapterSpec,
    SourceLocation,
)

EXTRACTOR_NAME = "mia-html-evidence"
EXTRACTOR_VERSION = "1"


class ExtractionDependencyError(ExtractionError):
    """A selected loader or extraction strategy is not installed."""


class ProductUrlRejectedError(ExtractionError):
    """A URL is outside the reviewed site's explicit allow-list."""


class RequiredEvidenceMissingError(ExtractionError):
    """A required extraction rule did not produce a value."""


class PageLoadError(ExtractionError):
    """The configured page loader could not return usable HTML."""


@dataclass(frozen=True, slots=True)
class RenderedPage:
    """Framework-neutral result of loading and rendering one web page."""

    url: str
    html: str
    acquired_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.url:
            raise ValueError("rendered page URL must not be empty")
        if self.acquired_at.tzinfo is None or self.acquired_at.utcoffset() is None:
            raise ValueError("rendered page acquisition time must include a timezone")

    @property
    def content_sha256(self) -> str:
        """Hash the exact UTF-8 HTML used by every evidence record."""

        return hashlib.sha256(self.html.encode("utf-8")).hexdigest()


class PageLoader(Protocol):
    """Load a URL into a framework-neutral rendered page."""

    async def load(self, url: str) -> RenderedPage: ...


class Crawl4AIPageLoader:
    """Optional Crawl4AI-backed renderer with no import-time dependency."""

    async def load(self, url: str) -> RenderedPage:
        try:
            from crawl4ai import AsyncWebCrawler
        except ImportError as exc:  # pragma: no cover - depends on optional install
            raise ExtractionDependencyError(
                "Crawl4AI is not installed; install the crawl runtime to load live pages"
            ) from exc

        try:
            async with AsyncWebCrawler() as crawler:
                result = await crawler.arun(url=url)
        except Exception as exc:  # pragma: no cover - upstream/browser failure
            raise PageLoadError(f"Crawl4AI could not load {url!r}: {exc}") from exc

        if not getattr(result, "success", False):
            detail = getattr(result, "error_message", None) or "unknown crawler error"
            raise PageLoadError(f"Crawl4AI could not load {url!r}: {detail}")

        html = getattr(result, "html", None)
        if not isinstance(html, str) or not html:
            raise PageLoadError(f"Crawl4AI returned no HTML for {url!r}")

        final_url = getattr(result, "redirected_url", None) or getattr(result, "url", None)
        return RenderedPage(
            url=final_url if isinstance(final_url, str) and final_url else url,
            html=html,
        )


class Crawl4AIWebsiteExtractor:
    """Public upstream adapter implementing MIA's small extraction interface."""

    def __init__(self, loader: PageLoader | None = None) -> None:
        self._loader = loader or Crawl4AIPageLoader()

    async def extract_url(
        self,
        url: str,
        spec: SiteAdapterSpec,
    ) -> tuple[EvidenceRecord, ...]:
        return await HtmlEvidenceExtractor(spec).extract_url(url, self._loader)


@dataclass(frozen=True, slots=True)
class _ExtractedValue:
    value: Any
    location: SourceLocation


class HtmlEvidenceExtractor:
    """Apply one reviewed ``SiteAdapterSpec`` without invoking an LLM."""

    def __init__(self, spec: SiteAdapterSpec) -> None:
        if not spec.approved:
            raise ExtractionError("site adapter must be approved before extraction")
        self._spec = spec
        self._validate_site_origin()

    async def extract_url(self, url: str, loader: PageLoader) -> tuple[EvidenceRecord, ...]:
        """Validate before loading, then validate the final URL after redirects."""

        self.validate_product_url(url)
        page = await loader.load(url)
        self.validate_product_url(page.url)
        return self.extract(page)

    def extract(self, page: RenderedPage) -> tuple[EvidenceRecord, ...]:
        """Extract evidence in declared rule order and document order."""

        self.validate_product_url(page.url)
        soup, xpath_tree = self._parse_html(page.html)
        records: list[EvidenceRecord] = []

        for rule in self._spec.field_rules:
            values = self._apply_rule(rule, soup, xpath_tree)
            if not values and rule.required:
                raise RequiredEvidenceMissingError(
                    f"required predicate {rule.predicate!r} produced no value"
                )
            if not rule.many:
                values = values[:1]

            for occurrence, extracted in enumerate(values):
                records.append(
                    EvidenceRecord(
                        id=self._evidence_id(
                            page=page,
                            rule=rule,
                            occurrence=occurrence,
                            value=extracted.value,
                        ),
                        predicate=rule.predicate,
                        value=extracted.value,
                        unit=rule.unit,
                        source_uri=page.url,
                        source_content_sha256=page.content_sha256,
                        source_location=extracted.location,
                        extraction_method=rule.source.value,
                        extractor_name=EXTRACTOR_NAME,
                        extractor_version=EXTRACTOR_VERSION,
                        status=EvidenceStatus.OBSERVED,
                        acquired_at=page.acquired_at,
                    )
                )

        return tuple(records)

    def validate_product_url(self, url: str) -> None:
        """Reject non-HTTP, unapproved-host, and non-product URLs."""

        try:
            parsed = urlsplit(url)
            hostname = parsed.hostname
        except ValueError as exc:
            raise ProductUrlRejectedError(f"invalid product URL {url!r}") from exc

        if parsed.scheme.casefold() not in {"http", "https"} or not hostname:
            raise ProductUrlRejectedError("product URL must be an absolute HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ProductUrlRejectedError("product URL must not contain credentials")

        allowed_hosts = {self._normalize_allowed_host(item) for item in self._spec.allowed_hosts}
        if hostname.casefold().rstrip(".") not in allowed_hosts:
            raise ProductUrlRejectedError(f"host {hostname!r} is not approved by the site adapter")

        try:
            matches_product = any(
                re.fullmatch(pattern, parsed.path) is not None
                for pattern in self._spec.product_url_patterns
            )
        except re.error as exc:
            raise ExtractionError(
                f"site adapter contains an invalid product URL pattern: {exc}"
            ) from exc
        if not matches_product:
            raise ProductUrlRejectedError(
                f"path {parsed.path!r} does not match an approved product URL pattern"
            )

    def _validate_site_origin(self) -> None:
        parsed = urlsplit(self._spec.site_origin)
        hostname = parsed.hostname
        if parsed.scheme.casefold() not in {"http", "https"} or not hostname:
            raise ExtractionError("site adapter origin must be an absolute HTTP(S) URL")
        allowed_hosts = {self._normalize_allowed_host(item) for item in self._spec.allowed_hosts}
        if hostname.casefold().rstrip(".") not in allowed_hosts:
            raise ExtractionError("site adapter origin host is absent from allowedHosts")

    @staticmethod
    def _normalize_allowed_host(value: str) -> str:
        candidate = value.strip()
        if not candidate:
            raise ExtractionError("allowedHosts must not contain empty values")
        try:
            parsed = urlsplit(candidate if "://" in candidate else f"//{candidate}")
            hostname = parsed.hostname
        except ValueError as exc:
            raise ExtractionError(f"invalid allowed host {value!r}") from exc
        if not hostname:
            raise ExtractionError(f"invalid allowed host {value!r}")
        return hostname.casefold().rstrip(".")

    @staticmethod
    def _parse_html(html: str) -> tuple[Any, Any]:
        try:
            from bs4 import BeautifulSoup
            from lxml import html as lxml_html
        except ImportError as exc:  # pragma: no cover - installation failure
            raise ExtractionDependencyError(
                "HTML extraction requires beautifulsoup4 and lxml"
            ) from exc

        soup = BeautifulSoup(html, "html.parser")
        try:
            xpath_tree = lxml_html.fromstring(html)
        except (TypeError, ValueError) as exc:
            raise ExtractionError(f"rendered page does not contain parseable HTML: {exc}") from exc
        return soup, xpath_tree

    def _apply_rule(
        self, rule: ExtractionRule, soup: Any, xpath_tree: Any
    ) -> list[_ExtractedValue]:
        try:
            if rule.source is ExtractionSource.CSS:
                return self._extract_css(rule, soup)
            if rule.source is ExtractionSource.META:
                return self._extract_meta(rule, soup)
            if rule.source is ExtractionSource.XPATH:
                return self._extract_xpath(rule, xpath_tree)
            if rule.source is ExtractionSource.JSON_LD:
                return self._extract_json_ld(rule, soup)
        except ExtractionError:
            raise
        except Exception as exc:
            raise ExtractionError(
                f"failed to apply {rule.source.value} rule for {rule.predicate!r}: {exc}"
            ) from exc
        raise ExtractionError(f"unsupported extraction source {rule.source!r}")

    @classmethod
    def _extract_css(cls, rule: ExtractionRule, soup: Any) -> list[_ExtractedValue]:
        result: list[_ExtractedValue] = []
        for node in soup.select(rule.selector):
            value = cls._value_from_html_node(node, rule.attribute)
            if cls._is_empty(value):
                continue
            result.append(
                _ExtractedValue(
                    value=value,
                    location=SourceLocation(
                        selector=rule.selector,
                        excerpt=cls._excerpt(value),
                    ),
                )
            )
        return result

    @classmethod
    def _extract_meta(cls, rule: ExtractionRule, soup: Any) -> list[_ExtractedValue]:
        attribute = rule.attribute or "content"
        result: list[_ExtractedValue] = []
        for node in soup.select(rule.selector):
            value = cls._value_from_html_node(node, attribute)
            if cls._is_empty(value):
                continue
            result.append(
                _ExtractedValue(
                    value=value,
                    location=SourceLocation(
                        selector=rule.selector,
                        excerpt=cls._excerpt(value),
                    ),
                )
            )
        return result

    @classmethod
    def _extract_xpath(cls, rule: ExtractionRule, xpath_tree: Any) -> list[_ExtractedValue]:
        result: list[_ExtractedValue] = []
        matches = xpath_tree.xpath(rule.selector)
        if not isinstance(matches, list):
            matches = [matches]
        for node in matches:
            if rule.attribute is not None:
                getter = getattr(node, "get", None)
                value = getter(rule.attribute) if getter is not None else None
            elif hasattr(node, "itertext"):
                value = cls._normalize_text(" ".join(node.itertext()))
            elif isinstance(node, str):
                value = cls._normalize_text(node)
            elif isinstance(node, (bool, int, float)):
                value = node
            else:
                value = str(node)
            if cls._is_empty(value):
                continue
            result.append(
                _ExtractedValue(
                    value=value,
                    location=SourceLocation(
                        selector=rule.selector,
                        excerpt=cls._excerpt(value),
                    ),
                )
            )
        return result

    @classmethod
    def _extract_json_ld(cls, rule: ExtractionRule, soup: Any) -> list[_ExtractedValue]:
        result: list[_ExtractedValue] = []
        scripts = soup.select('script[type="application/ld+json"]')
        for script_index, script in enumerate(scripts):
            raw = script.string if script.string is not None else script.get_text()
            try:
                document = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            for entity in cls._json_ld_entities(document):
                found, value = cls._resolve_json_pointer(entity, rule.selector)
                if not found:
                    continue
                values = value if rule.many and isinstance(value, list) else [value]
                for item in values:
                    if cls._is_empty(item):
                        continue
                    result.append(
                        _ExtractedValue(
                            value=item,
                            location=SourceLocation(
                                selector=(
                                    f"script[type='application/ld+json'] (match {script_index + 1})"
                                ),
                                json_pointer=rule.selector,
                                excerpt=cls._excerpt(item),
                            ),
                        )
                    )
        return result

    @staticmethod
    def _json_ld_entities(document: Any) -> list[Any]:
        if isinstance(document, list):
            return document
        if isinstance(document, dict):
            graph = document.get("@graph")
            if isinstance(graph, list):
                return [document, *graph]
        return [document]

    @staticmethod
    def _resolve_json_pointer(document: Any, pointer: str) -> tuple[bool, Any]:
        if pointer == "":
            return True, document
        if not pointer.startswith("/"):
            raise ExtractionError(f"JSON-LD selector {pointer!r} is not a JSON Pointer")

        current = document
        for raw_token in pointer[1:].split("/"):
            token = raw_token.replace("~1", "/").replace("~0", "~")
            if isinstance(current, dict) and token in current:
                current = current[token]
                continue
            if isinstance(current, list):
                try:
                    index = int(token)
                except ValueError:
                    return False, None
                if 0 <= index < len(current):
                    current = current[index]
                    continue
            return False, None
        return True, current

    @classmethod
    def _value_from_html_node(cls, node: Any, attribute: str | None) -> Any:
        if attribute is None:
            return cls._normalize_text(node.get_text(" ", strip=True))
        value = node.get(attribute)
        if isinstance(value, list):
            return " ".join(str(item) for item in value)
        return cls._normalize_text(value) if isinstance(value, str) else value

    @staticmethod
    def _normalize_text(value: str) -> str:
        return " ".join(value.split())

    @staticmethod
    def _is_empty(value: Any) -> bool:
        return value is None or (isinstance(value, str) and not value.strip())

    @staticmethod
    def _excerpt(value: Any) -> str:
        if isinstance(value, str):
            rendered = value
        else:
            rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return rendered[:240]

    def _evidence_id(
        self,
        *,
        page: RenderedPage,
        rule: ExtractionRule,
        occurrence: int,
        value: Any,
    ) -> str:
        identity = json.dumps(
            {
                "adapter": self._spec.id,
                "adapter_version": self._spec.version,
                "content_sha256": page.content_sha256,
                "occurrence": occurrence,
                "predicate": rule.predicate,
                "selector": rule.selector,
                "source": rule.source.value,
                "url": page.url,
                "value": value,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"evidence:{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"
