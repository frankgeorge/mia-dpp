# MIA Backend Reduction Plan

## Purpose

Make the current backend easier to read, debug, and maintain without changing MIA's product behavior. Code reduction is a consequence of removing duplicate concepts and forwarding layers; it is not a quota.

The current architecture remains:

```text
FastAPI -> Mia -> PydanticAI -> agent tools -> deterministic capabilities -> Store
```

The following guarantees remain non-negotiable:

- source evidence and provenance are retained;
- deterministic mapping runs before semantic reasoning;
- official template identifiers come only from official template data;
- only trusted API actions can approve mappings or create human evidence;
- coverage, AAS compilation, and AAS validation remain deterministic;
- deferred human work survives a process restart;
- current frontend/API behavior and artifact access remain functional.

This plan starts from `dev/pratik` at `709b58a` with 56 production Python files and 7,828 lines under `backend/src/mia_dpp`.

## What is still too complex

| Area | Current lines | Main problem |
|---|---:|---|
| `tools/mapping/` | 1,596 | One capability is divided across ten modules and several overlapping mapping/result models. |
| `aas/` | 1,634 | Necessary standards logic is mixed with stateless service classes and duplicate target/build contracts. |
| `agent/` | 1,278 | The 921-line tool module repeats state lookup, event creation, artifact writing, and status updates. |
| `domain/` | 776 | Target, mapping, coverage, and completion views overlap rather than sharing one authoritative record. |
| `store.py` | 592 | One store is correct, but session, deferral, knowledge, artifact, and export operations repeat SQLite/JSON mechanics. |
| `mia.py` | 532 | The orchestration is centralized correctly, but human resume and persistence paths still repeat lifecycle work. |
| `tools/web/` | 619 | Raw page, raw artifact, candidate fact, extraction result, and knowledge-package transitions carry overlapping data. |

The most important duplication is currently:

```text
ProductWork
  -> WebExtractionResult
       -> ProductKnowledgePackage
            -> EvidenceRecord[]
  -> ProductResolution
       -> ProductKnowledgePackage       # the evidence appears again
       -> MappingResult
       -> TemplateIndex
       -> computed CoverageReport
       -> computed CompletionSummary
```

The state should instead make the authoritative data obvious:

```text
ProductWork
  -> sources
  -> evidence
  -> mappings
  -> pending human request
  -> generated artifact IDs

TemplateIndex is loaded from the official repository.
Coverage and completion are derived when requested.
```

## Architectural budgets

These are warning thresholds, not targets to game.

- No class unless it owns state/lifecycle, validates a meaningful contract, or provides a real provider/test boundary.
- No protocol unless the application has multiple implementations or tests genuinely substitute it.
- No persisted model for data that is cheap and deterministic to derive.
- No service/coordinator whose removal would only make the caller invoke another object directly.
- No second authoritative representation of evidence, mappings, reviews, or artifacts.
- No compatibility layer without a named deletion stage.
- No module split solely because of line count.
- No dependency unless it removes more complexity than it introduces.
- Prefer `mia.py` below roughly 450 lines; do not move its lifecycle into another wrapper to hit that number.
- Keep model-visible tools explicit and semantically named, even when they share small internal helpers.
- Mapping may remain the largest MIA-specific area because that is where MIA owns real domain behavior.

## Final authoritative data model

Persist only records needed to recover or audit work independently:

### Persisted

1. `Session`
   - thread ID, user goal, selected company/product identities, queue/current product, status, and pending human call identity.
2. PydanticAI message history
   - stored separately from workflow facts but under the same session ID.
3. `Source`
   - selected URL and provenance metadata for each acquired source.
4. `Evidence`
   - one canonical evidence record per fact, associated with product and source.
5. `Mapping`
   - evidence ID, authoritative target ID/path, basis, status, explanation, and semantic-review summary when applicable.
6. `ReviewEvent`
   - immutable human approve/correct/reject/value action, call ID, timestamp, and optional comment. This remains separate because audit history and replay protection are real requirements.
7. `MappingKnowledge`
   - only human-confirmed reusable mapping knowledge; it references reviewed evidence/mapping rather than copying full product state.
8. `Artifact`
   - metadata and lineage in SQLite; bytes remain in the thread-isolated artifact directory.
9. Pending/resolved deferred calls
   - call ID, expected action, trusted result, and status required for crash-safe resume.

These records may remain serialized inside a compact session snapshot during the migration. The final store layout should be chosen for the simplest correct recovery path, not relational purity.

### Derived, not authoritative

- `ProductResolution` wrapper;
- combined web extraction result;
- mapping statistics;
- coverage statistics and requirement rows;
- completion summary;
- source-fact counts;
- workspace tree and combined export;
- selectable target catalog;
- current response projection;
- user-visible activity summaries.

Derived views may have small response models when the API benefits from validation, but they are recalculated from evidence, mappings, templates, and artifacts.

## Proposed cohesive module structure

The goal is fewer concepts and shorter debugging paths, not a flat-file contest.

```text
backend/src/mia_dpp/
├── main.py                     # FastAPI construction and router attachment
├── mia.py                      # complete autonomous turn/defer/resume lifecycle
├── config.py                   # environment-backed settings
├── store.py                    # SQLite sessions, history, deferrals, knowledge, artifact metadata
├── errors.py                   # public application error taxonomy
│
├── api/
│   ├── routes.py               # HTTP transport only
│   └── schemas.py              # HTTP-only input/output contracts
│
├── agent/
│   ├── models.py               # minimal session/job and agent-output contracts
│   ├── prompts.py              # model instructions only
│   └── tools.py                # small model-visible state-transition functions
│
├── domain/
│   ├── models.py               # Evidence, Mapping, ReviewEvent and shared wire base
│   └── templates.py            # Target, TemplateRelease and TemplateIndex contracts
│
├── tools/
│   ├── search.py               # one provider-neutral search capability and three semantic projections
│   ├── web/
│   │   ├── extract.py          # page -> provenance-backed evidence
│   │   ├── models.py           # PageLoader boundary and minimal page/extraction data
│   │   └── url_policy.py       # SSRF and URL validation boundary
│   ├── mapping/
│   │   ├── map.py              # exact/known rules and authoritative target mapping
│   │   ├── rules.py            # deterministic mapping data and parsers
│   │   └── review.py           # semantic proposal validation and trusted human application
│   └── documents.py            # optional document -> evidence capability
│
├── aas/
│   ├── templates.py            # official repository loading and the single TemplateIndex
│   ├── build.py                # accepted mappings -> AAS package
│   └── validate.py             # aas-core plus retained IDTA-specific checks
│
└── integrations/
    ├── crawl4ai.py             # PageLoader implementation
    ├── ddgs.py                 # search implementation
    ├── pdf2aas.py              # optional PDF preprocessor
    └── basyx.py                # optional deployment integration
```

This is an expected result, not a mandate to move code for aesthetics. In particular, `_structure.py` may remain if sharing its small AAS traversal helpers is clearer than duplicating them.

## Concrete reductions by area

### 1. Canonical product state and models

Replace the nested `extractions` plus `ProductResolution` graph with direct authoritative product collections:

```text
ProductWork.sources
ProductWork.evidence
ProductWork.mappings
ProductWork.pending_reviews
ProductWork.artifact_ids
```

Planned removals/consolidations:

- delete `ProductResolution` after all callers consume the canonical collections;
- remove the repeated `ProductKnowledgePackage` stored inside resolution;
- replace `combined_extraction()` object reconstruction with evidence/source deduplication at insertion time;
- collapse `MappingDraft`, `FieldMapping`, `ProposedFieldMapping`, and `ApprovedMapping` where one `Mapping` plus status/basis fields preserves all behavior;
- retain an immutable review record because human authority and audit history justify it;
- merge completion response models into one derived API projection or plain typed result;
- keep the frontend JSON shape temporarily through a response projection, then remove it after frontend migration.

Expected reduction: 350–550 lines.

### 2. Template and target unification

Make one `Target` record in `TemplateIndex` serve mapping, coverage, review, build, and validation.

Planned removals/consolidations:

- unify `Requirement`, `MappingTarget`, and `NameplateElement` around one indexed target identity;
- remove `TargetProfile` if release metadata on `TemplateIndex` is sufficient for compilation;
- derive selectable catalogs by filtering the index;
- merge `aas/requirements.py` into template indexing;
- ensure wildcard/structural/cardinality metadata stays present, because aas-core alone does not provide MIA's IDTA completion rules.

Expected reduction: 250–400 lines.

### 3. Mapping capability

Keep mapping custom, but reduce orchestration and intermediate objects.

Planned structure:

```text
map_evidence(evidence, index, known_rules) -> tuple[Mapping, ...]
coverage(index, mappings) -> CoverageView
validate_semantic_proposal(proposal, index, evidence) -> Mapping
apply_human_review(mapping, decision) -> Mapping + ReviewEvent
```

Planned removals/consolidations:

- delete `resolver.py`; its current function only loads templates, calls the mapper, evaluates coverage, and wraps the result;
- merge the 138-line mapper with its target construction where that makes the rule path linear;
- keep large deterministic text-pattern data separate as `rules.py`, preferably represented as immutable data rather than many construction branches;
- collapse confidence enums and assessment plumbing to `MappingBasis`, `review_required`, and concise reasons;
- reduce coverage to direct matching/accounting over `TemplateIndex` and accepted/proposed mappings;
- derive completion from the same coverage result rather than maintaining a second accounting subsystem;
- preserve semantic target validation and mapping-knowledge scoping in review logic.

Expected reduction: 550–850 lines.

### 4. Agent tool adapters

Keep meaningful model-visible tools, but remove repeated ceremony.

Each tool should visibly do only:

```text
check prerequisite -> call capability -> update canonical state -> persist useful output -> return observation
```

Use two or three private functions only where they remove repeated product lookup, artifact creation, or status transition code. Do not add a tool manager or coordinator.

Planned reductions:

- stop writing duplicate source/evidence/mapping/coverage payloads when the same canonical data is already addressable;
- centralize one artifact-and-activity write operation in `MiaDependencies` or `Store`;
- remove repeated state reassignments after mutating the same `ProductWork`;
- pass `TemplateIndex` and canonical evidence/mappings directly to capability functions;
- preserve all current semantic tool names because they improve model tool selection.

Expected reduction: 220–350 lines.

### 5. User activity and tracing

Keep user-visible progress but remove the remaining duplicate trace authority.

Current events live both in `MiaState.trace` and as trace artifacts. Replace that with one append-only store event stream. Responses query events after an offset; the frontend continues polling the same API projection.

Persist only safe product activity events:

```text
searching, extracting, mapping, waiting_for_review,
building_aas, completed, failed
```

Provider/model telemetry belongs to PydanticAI/OpenTelemetry instrumentation and does not get reimplemented in MIA.

Expected reduction: 100–180 lines.

### 6. Store

Retain direct `sqlite3`; an ORM would add more concepts than it removes at this scale.

Planned reductions:

- use one transaction helper and compact row conversion functions;
- store event rows directly rather than creating one JSON artifact per activity event;
- remove duplicate combined-export assembly paths;
- keep path validation, thread isolation, content hashing, replay protection, and atomic defer/resume transactions even if they cost lines;
- keep one `Store` class because it owns a real SQLite connection/schema lifecycle.

Expected reduction: 80–160 lines.

### 7. Web extraction

Keep the `PageLoader` boundary, URL policy, Crawl4AI integration, generic extraction, and provenance.

Planned reductions:

- remove `RawSourceArtifact` when `RenderedPage` plus stored artifact metadata carries the same information;
- have the extractor produce normalized evidence without a separately instantiated stateless normalizer;
- merge `artifacts.py` into extraction/storage call sites;
- retain `CandidateFact` only if it remains useful for deduplicating facts before provenance IDs are assigned;
- keep trusted committed Crawl4AI schemas as data; generated schemas remain untrusted runtime candidates until reviewed against fixtures/source.

Expected reduction: 100–180 lines.

### 8. AAS build and validation

This area should shrink conservatively.

Planned reductions:

- replace stateless `AasCompiler`, `AasValidator`, and `DeterministicDppPipeline` objects with functions if constructor state is not required;
- make build and validation consume the same `TemplateIndex` and accepted mappings;
- remove duplicate specification/profile wrappers;
- preserve official-template integrity checks, IDTA path/cardinality/wildcard rules, value-type validation, semantic-ID validation, and aas-core verification;
- keep compiler and validator separate because construction and verification are independently testable responsibilities.

Expected reduction: 250–400 lines.

### 9. API and compatibility projection

Do this last.

- preserve current routes while the internal model changes;
- migrate frontend types to the canonical response once backend behavior is stable;
- remove temporary old response projections, obsolete schemas, and unused route fields in the final deletion commit;
- retain `/api/dpp` while the frontend calls it, or migrate and delete both caller and route in the same commit.

Expected reduction: 70–140 lines.

## Estimated result

The ranges above overlap, so they must not be summed mechanically. A defensible target is:

```text
Current post-refactor backend:     7,828 lines
Expected lean backend:             5,400–5,900 lines
Expected additional reduction:     1,928–2,428 lines
Reduction from current state:       24.6–31.0%

Original pre-lean backend:         8,770 lines
Expected cumulative reduction:     32.7–38.4%
```

Expected production Python file count:

```text
Current: 56
Expected: approximately 36–42
```

The lower line target is acceptable only if regression tests and the real AFRISO flow continue to pass. If reaching it would require deleting standards checks, provenance, trusted human boundaries, or crash recovery, the correct outcome is a smaller percentage.

## Migration sequence

Every phase is one cohesive commit unless a test-discovered correction needs its own commit.

### Phase 0 — Record behavior and measurements

Goal:

- capture the current tree, LOC, API schemas, artifact shapes, and AFRISO tool sequence;
- add only missing high-value regression tests needed to make later deletion safe.

Required tests:

- direct URL is used without URL confirmation;
- repeated URL extraction is not repeated;
- deterministic mapping output remains identical for fixtures;
- semantic mapping cannot select an unknown official target;
- the model cannot forge human approval/evidence;
- defer/resume survives process restart and rejects replay/wrong call IDs;
- compiled AAS and validation findings remain identical for fixtures.

Rollback boundary: current `709b58a` plus the already-pushed snapshot branch.

### Phase 1 — Make product data authoritative once

Goal:

- reshape `ProductWork` around sources, evidence, mappings, reviews, and artifact IDs;
- remove `ProductResolution` and nested duplicated knowledge packages.

Temporary compatibility:

- one response projection may reproduce the old frontend payload.

Deletion stage: Phase 7.

Tests:

- state serialization/reload;
- multi-source evidence deduplication;
- mapping/review persistence;
- current agent/API regression suite.

### Phase 2 — Unify template targets

Goal:

- introduce the final compact `Target`/`TemplateIndex` representation;
- migrate mapping, catalog, coverage, build, and validation consumers.

Remove:

- overlapping requirement/mapping-target/catalog element representations;
- standalone requirements builder module if indexing belongs naturally in templates.

Tests:

- official-template hashes/releases;
- cardinality and wildcard classification;
- target path and semantic-ID resolution;
- all AAS tests.

### Phase 3 — Collapse mapping and derived completion

Goal:

- make the evidence-to-mapping path readable in a few functions;
- derive coverage/completion from the target index and mappings.

Remove:

- resolver coordinator;
- duplicate mapping variants;
- redundant completion statistics models;
- remaining assessment data not used by policy or UI.

Tests:

- golden deterministic AFRISO mappings;
- unmatched/rejected evidence retention;
- exact/known/semantic/human bases;
- mapping-knowledge scope;
- mandatory/optional/technical coverage invariants.

### Phase 4 — Slim agent tools and activity

Goal:

- keep semantic model-visible operations while reducing repeated state/artifact/event code;
- establish one user-activity event authority in `Store`.

Remove:

- trace tuple from session state;
- per-event trace artifacts;
- repeated tool boilerplate that has no distinct policy.

Tests:

- multi-tool autonomous run;
- events visible before run completion;
- no duplicate frontend activity;
- no hidden model reasoning in events.

### Phase 5 — Simplify web extraction and persistence mechanics

Goal:

- reduce page-to-evidence representations;
- simplify SQLite helpers without weakening safety.

Remove:

- duplicate raw artifact representation;
- stateless forwarding normalizer/artifact modules where proven redundant;
- repeated store transaction/row-conversion code.

Tests:

- generic fixture extraction remains byte-for-byte or semantically equivalent;
- URL/SSRF rejection;
- provenance and hashes;
- artifact isolation/read/download/ZIP;
- crash-safe deferred resume.

### Phase 6 — Simplify deterministic AAS boundary

Goal:

- use direct build/validate functions over the shared index and mappings;
- retain only checks not supplied by aas-core or official template data.

Remove:

- stateless service classes;
- specification/profile wrappers no longer carrying independent information;
- duplicate template interpretations.

Tests:

- fixture output equivalence;
- aas-core verification;
- missing mandatory field;
- bad semantic ID/path/type/unit/cardinality;
- wildcard extension behavior;
- official template version/integrity.

### Phase 7 — Migrate API/frontend projection and delete compatibility

Goal:

- expose the canonical state-derived response;
- update frontend types/components;
- delete the Phase 1 compatibility projection and stale endpoints/fields.

Tests:

- full frontend typecheck/build;
- agent chat, review/value submission, coverage, workspace, artifact download;
- Docker Compose and production entrypoint.

### Phase 8 — Final deletion and audit

Goal:

- run the delete test on every production module, class, model, and dependency;
- remove dead imports, exports, tests of removed wrappers, and obsolete documentation;
- verify there is exactly one path for each capability.

Commands/checks:

```text
make check
stale-import searches
dependency audit
production LOC/file/model counts
mia_dpp.main:app import
real AFRISO TankControl 25 smoke test
```

## Delete test

For every existing abstraction:

```text
If this is deleted, what user-visible, safety, provider, lifecycle,
or independently testable capability disappears?
```

If the answer is only “the caller invokes the next object directly,” delete or inline it.

For every proposed helper/class:

```text
What policy, state, lifecycle, or substitution boundary does it own?
```

If there is no concrete answer, do not add it.

## Things that must not be simplified away

Some code is justified even when it prevents a larger reduction:

- SSRF protection, DNS/IP validation, and artifact path isolation;
- evidence identifiers, source locations, hashes, and lineage;
- official-template release/hash verification;
- IDTA cardinality, structure, wildcard, and semantic-ID rules not covered by aas-core;
- deterministic value/type/unit validation;
- rejected and unmatched evidence retention;
- human-only approval and human-evidence creation;
- immutable review audit events and deferred-call replay protection;
- atomic persisted defer/resume behavior;
- source-first and mandatory-before-optional policy;
- real multi-product terminal-state accounting.

## Definition of done

The reduction is complete when:

1. one fact has one authoritative in-memory/persisted representation;
2. `mia.py` still shows the entire autonomous lifecycle;
3. each agent tool has a short, visible state transition and delegates real algorithms;
4. mapping can be followed from evidence to accepted/reviewed target without wrapper hopping;
5. one `TemplateIndex` drives mapping, coverage, build, and validation;
6. coverage and completion are derived, not separately authoritative;
7. one store owns sessions, history, deferrals, knowledge, event rows, and artifact metadata;
8. frontend/API compatibility code introduced during migration has been deleted;
9. full checks and the AFRISO live smoke pass;
10. the achieved reduction is reported honestly, including code deliberately retained for correctness.

