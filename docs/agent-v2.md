# MIA Agent V2

Agent V2 adds one model-led plan/act/observe loop without weakening MIA's deterministic
evidence and AAS rules.

```text
user message
    ↓
PydanticAI Agent
    ├─ search company / select company
    ├─ discover products / select products
    ├─ extract one or more product sources
    ├─ map retained evidence deterministically
    ├─ inspect and propose bounded semantic mappings
    ├─ record human evidence or review decisions
    └─ build AAS through deterministic gates
             ↓
      observation + updated typed state
             ↓
        reason again or stop for the user
```

## Framework choices

The runtime pins PydanticAI 2.43.0. It uses `Agent` for the autonomous loop, typed
`RunContext` dependencies for tool access, `Tool` for the small model-visible capability
surface, a structured `AgentRunOutput`, server-supplied `message_history`, and the core
`Capability` API for the `dpp-creation` task instructions.

PydanticAI Harness Skills are not used yet. Their separate 0.x package would add a second
runtime dependency for one instruction bundle; the stable core `Capability` provides the
needed skill semantics without hiding Python rules in prose.

OpenRouter uses PydanticAI's official `OpenRouterModel` and `OpenRouterProvider` for Agent
V2. The older MIA OpenRouter client remains only because the migration-only LangGraph
endpoint still uses the old chat and semantic roles.

## Tool, skill, state, and memory

- A **tool** performs a typed action: public discovery, evidence extraction, deterministic
  mapping, human-evidence recording, or AAS building.
- A **skill/capability** tells the agent how to approach DPP creation. Deterministic
  invariants remain Python validation, not prompt text.
- **Conversation history** is PydanticAI model-message history. The server loads it by
  `thread_id`; the browser cannot submit trusted tool history.
- **Workflow state** is `MiaState`: selected companies/products, product queues, evidence,
  mappings, reviews, source candidates, target templates, artifacts, and safe trace events.
- **Long-term memory** is deliberately deferred. Thread history is not presented as learned
  knowledge. Approved adapters and mapping relationships need a separate reviewed store.

The development store is SQLite (`MIA_THREAD_STORE_PATH`, defaulting to
`/tmp/mia-agent-v2.sqlite3`). State JSON and PydanticAI messages are stored separately behind
the `ThreadStore` protocol, so a durable production store can replace SQLite.

## Current model-visible capabilities

The agent sees a deliberately small surface:

```text
search_companies                 public company identity candidates
select_company                  accept an exact candidate ID
discover_products               manufacturer-domain product candidates
select_products                 create a sequential multi-product queue
extract_product_page            URL → provenance-rich evidence
research_product_sources        find another relevant/official source
map_product_evidence            deterministic mapping and coverage
inspect_unresolved_mappings     bounded evidence + allowed official requirements
propose_semantic_mapping        AI proposal, constrained and review-required
review_semantic_mapping         apply a human approve/correct/reject decision
record_human_requirement_value  human answer → provenance-aware evidence
build_product_aas               deterministic completeness/build/validation gate
```

DDGS 9.16.0 supplies key-free structured public search behind the provider-neutral
`SearchProvider`. It is suitable for an MVP and degrades to a typed unavailable result. It is
not an authoritative company registry: MIA marks manufacturer-domain matches and asks the
user when identity remains ambiguous.

## Autonomy versus authority

The model decides which capability to call and can repeat research, extraction, and mapping.
Python remains authoritative:

- web facts must have source provenance;
- deterministic mapping runs before semantic proposals;
- semantic proposals can reference only retained evidence and registered official targets;
- model-produced confidence is ignored; MIA calculates explainable confidence factors;
- rejected proposals do not delete evidence;
- human answers become `SourceType.HUMAN` evidence;
- official templates, the compiler, and validator determine whether an AAS is valid.

The activity panel renders explicit `AgentTraceEvent` records. These are safe action summaries,
not hidden chain-of-thought.

Semantic review is stored as typed `SemanticReviewItem` state and resumed through the trusted
review endpoint. PydanticAI deferred-tool approval was evaluated, but the existing MIA interaction
needs approve, reject, corrected target, and corrected value—not only permission to execute one
pending call. Keeping the richer decision object server-side preserves that contract while the
PydanticAI agent remains the only model-led decision loop.

## Migration status and limits

The workspace now calls `/api/agent/v2/messages` and `/api/agent/v2/review`. The old
LangGraph endpoints remain temporarily as a rollback/migration path while live OpenRouter and
AFRISO smoke testing is completed. LangGraph is not called by Agent V2 and is not a second
decision-maker inside the V2 loop.

Current deliberate limits:

- trace events are returned after each run; live SSE event streaming is deferred;
- SQLite is a single-instance development store, not suitable for horizontally scaled Vercel
  containers;
- DDGS availability and ranking are best effort;
- semantic proposals use the main agent's bounded mapping capability rather than a separately
  deployed subagent;
- document extraction and BaSyx integration exist but are not yet model-visible V2 tools;
- only pinned Digital Nameplate and Technical Data templates are available; no missing official
  submodels are fabricated;
- multi-product state and sequential queues exist, but batch completion UI remains minimal.
