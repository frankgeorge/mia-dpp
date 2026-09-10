# Deterministic backend

MIA uses AI only to propose unfamiliar semantic decisions. The repeatable path
is ordinary typed Python:

```text
source -> EvidenceRecord -> reviewed MappingSpecification
       -> official IDTA template -> aas-core Environment
       -> metamodel + template validation -> deployable artifact
```

## Why the official templates are a submodule

`standards/idta-submodel-templates` is the unmodified upstream IDTA repository,
pinned to one commit in Git. It is standards data, not application code. MIA
reads it through `OfficialTemplateRepository`; only that adapter knows the
upstream directory layout.

The first two releases are deliberately bounded:

- Digital Nameplate 3.0.1 is used by the workspace.
- Technical Data 2.0.1 proves the loader and compiler support nested templates.

Both files are checked against known SHA-256 digests before use. Initialize the
submodule with `make refs` after a normal clone.

## Where each decision lives

| Concern | Code | Deterministic guarantee |
|---|---|---|
| API/domain contracts | `backend/src/mia_dpp/models.py` | Pydantic rejects unknown or inconsistent data. |
| Template ingestion | `templates.py` | Exact commit, path and content digest are checked. |
| Website extraction | `extraction.py` | An approved `SiteAdapterSpec` drives CSS, XPath, metadata and JSON-LD rules. |
| Website ingestion | `website.py` | Crawl4AI renders the page; MIA converts common structured fields into evidence and reuses the existing mapper. |
| PDF preprocessing | `documents.py` | BaSyx PDF-to-AAS is isolated behind a text-preprocessor interface. |
| Confidence | `confidence.py` | Five visible factors add up to the displayed score. |
| Demo evidence | `idta.py` | Regex rules produce provenance-rich evidence and official mapping targets. |
| Compilation | `aas.py` | Approved values are projected onto official template nodes and serialized by `aas-core`. |
| Pipeline | `pipeline.py` | Evidence, mapping, compilation, gaps and validation run in one order. |
| BaSyx deployment | `basyx.py` | Invalid, stale or modified artifacts are rejected before HTTP calls. |

## Confidence is a score, not a probability

Each mapping receives points for its source label, value format, semantic match,
destination ambiguity and independent corroboration. Every incomplete factor
adds a plain-language uncertainty. Previous human approvals can reduce target
ambiguity, but they never count as evidence that the current value is correct.

## Validation layers

1. Pydantic validates MIA's input contracts.
2. `aas-core3.0-python` parses the generated Environment and checks AAS 3.0
   metamodel constraints.
3. MIA compares hierarchy, cardinality, model type, value type and semantic IDs
   with the selected official IDTA template.
4. A failed report sets `deployable` to `false`; the BaSyx adapter refuses it.

The Digital Nameplate refers to Address Information as an external drop-in but
does not embed that template's children. MIA preserves the required structural
collection and reports this limitation as a warning instead of pretending deep
validation occurred.

## Current AI boundary

Without `OPENROUTER_API_KEY`, the complete local path is deterministic. With a
key, OpenRouter may propose source-to-target candidates. Python still resolves
targets from the pinned template, computes confidence, creates the AAS and
performs validation. An LLM-supplied semantic ID or confidence number is never
authoritative.
