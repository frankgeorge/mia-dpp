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
| Domain contracts | `domain/` | Pydantic rejects unknown or inconsistent data. |
| Template ingestion/index | `aas/templates.py`, `aas/requirements.py` | Exact commit, content digest, and one shared `TemplateIndex` are checked. |
| Website extraction | `tools/web/` | Crawl4AI renders; MIA retains common structured facts with provenance. |
| PDF preprocessing | `tools/documents/`, `integrations/pdf2aas.py` | Optional PDFium/pdf2aas code stays behind a text-preprocessor boundary. |
| Mapping policy | `tools/mapping/` | Exact rules, semantic proposals, and human decisions remain distinguishable. |
| Compilation | `aas/compiler.py` | Accepted values are projected onto official template nodes and serialized by `aas-core`. |
| Validation | `aas/validator.py` | Metamodel and IDTA-specific path/cardinality checks gate output. |
| BaSyx deployment | `integrations/basyx.py` | Invalid, stale, or modified artifacts are rejected before HTTP calls. |

## Mapping assessment is not a probability

Each mapping records an explicit basis (`exact`, `semantic`, or `human`), a
review decision, and plain-language uncertainties. No model-provided or
handcrafted numeric confidence is authoritative.

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
targets from the pinned template, applies review policy, creates the AAS and
performs validation. An LLM-supplied semantic ID or confidence value is never
authoritative.
