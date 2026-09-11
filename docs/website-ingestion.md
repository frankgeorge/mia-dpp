# Website ingestion: current capability and limits

MIA currently accepts a **direct, public product-page URL**. It does not yet
discover a product catalogue from a manufacturer's home page.

## What runs today

```text
direct product URL
  -> Crawl4AI page loader
  -> RawSourceArtifact (URL, acquisition time, content hash)
  -> generic CandidateFact extraction
  -> provenance-rich EvidenceRecord collection
  -> deterministic mapping attempt
  -> mapped, ambiguous, and unmatched outcomes
```

Fact extraction and mapping are deliberately separate. Every useful extracted
fact enters the product knowledge package before mapping starts. An unmatched
fact remains available to future semantic reasoning or human review.

The generic extractor currently reads:

- schema.org JSON-LD `Product` values;
- schema.org `additionalProperty` values;
- HTML specification tables;
- HTML definition lists (`dt` / `dd`);
- the page title and main `h1` product heading.

Each evidence record carries its source URL, source content SHA-256, acquisition
time, source label, extraction method, and a selector, JSON pointer, or table
location when available.

## What the deterministic mapper understands

The current mapper is intentionally narrow. It recognizes a subset of common
nameplate information such as manufacturer, model/designation, serial number,
order/article number, year of construction, country of origin, IP protection,
measuring ranges, and CE marking. Recognition does not make an uncertain target
authoritative: ambiguous mappings still require review.

Technical facts such as processor, protocol, material, voltage, current,
temperature, dimensions, and weight can be extracted even when the current
mapper has no official target for them. The Evidence view labels these facts as
unmatched instead of hiding them.

## Known limitations

- The submitted URL must be a direct product page. Site-wide crawling, catalogue
  discovery, product selection, and recursive research are not implemented.
- Extraction is limited to the structured HTML patterns listed above. Facts
  present only in prose, images, downloads, client-side API calls, or PDFs may be
  missed.
- Crawl4AI renders one page; it does not follow related product or datasheet
  links in this workflow.
- The deterministic mapper covers only its existing rules and the pinned
  Digital Nameplate template. It does not yet perform general semantic matching
  against every IDTA submodel.
- MIA retains source facts but does not persist the full acquired HTML after the
  request. The content hash provides identity; durable source-archive storage is
  a future concern.
- Website content and anti-bot controls can change, so a public page that works
  today may later require a reviewed site adapter.

## Suitable manual check

As of September 2026, the following direct product page worked with the current
single-page loader and exposed recognizable product information:

```text
https://www.ifm.com/us/en/product/PN7094
```

This URL is useful for a smoke test, not a permanent fixture. Automated tests
use the local HTML fixture in `backend/tests/fixtures/web/website-product.html`
so test results do not depend on the internet or a third-party website.

## Deferred architecture

Future semantic matchers, human-review strategies, and LangGraph orchestration
can consume `ProductKnowledgePackage`, `MappingResult`, and `WorkflowEvent`
without changing website extraction. No framework-specific message or graph
state is part of these domain contracts.
