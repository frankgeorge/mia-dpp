# MIA autonomous runtime

MIA has one autonomous decision-maker:

```text
user → FastAPI → Mia → PydanticAI agent
                            ↓
           search / extract / map / build tools
                            ↓
           deterministic evidence and AAS core
```

`Mia` loads trusted server-side state and message history, invokes PydanticAI,
and saves the resulting turn. PydanticAI chooses and repeats tools; there is no
second workflow graph choosing a business sequence.

## Authority and state

- PydanticAI decides what action to attempt.
- Deterministic Python decides what evidence, mapping, coverage, and AAS output is
  valid.
- Model tools may request human input. Only `/api/agent/review` and `/api/agent/value` can apply
  trusted human decisions or create human evidence.
- Conversation history and `MiaState` are separate values saved under one thread ID.
- Reviewed mapping knowledge is separate from both thread history and generated files.
- SQLite stores artifact metadata; generated files live under
  `MIA_WORKSPACE_ROOT/<thread_id>` and are resolved only through artifact IDs.

## Model-visible capabilities

```text
search_companies / select_company
discover_products / select_products
extract_product_page / research_product_sources
map_product_evidence / inspect_unresolved_mappings
propose_semantic_mapping
request_human_review / request_human_value
build_product_aas
```

The tools expose meaningful actions, while Crawl4AI, DDGS, and PydanticAI's OpenRouter provider
remain vendor integrations. Semantic proposals are bounded to retained evidence and official
targets. The model cannot approve them or assign authoritative mapping status.

## Observability and artifacts

Every run and tool action emits a safe `AgentTraceEvent`. These are decision/action summaries,
not private chain-of-thought. Search results, source metadata, evidence, mappings, coverage,
reviews, validation, and AAS output are written as artifacts with hashes and lineage.
The workspace UI can view individual files or download the complete ZIP.

Current limits: event delivery is request/response rather than SSE; local SQLite/filesystem
persistence is single-instance; DDGS results require verification; document extraction and BaSyx
deployment exist but are not model-visible tools; only the pinned template releases are used.
