# MIA autonomous runtime

MIA has one autonomous decision-maker and one workflow-lifetime owner:

```text
user → FastAPI → LangGraph lifecycle → PydanticAI brain
                                      ↓
                     search / extract / map / build tools
                                      ↓
                     deterministic evidence and AAS core
```

LangGraph stores checkpoints, thread state, PydanticAI message history, human interrupts,
and reusable memory. Its graph has only an autonomous-agent node and a human-interrupt node;
it does not choose a business sequence. PydanticAI chooses and repeats tools inside the
autonomous node.

## Authority and state

- PydanticAI decides what action to attempt.
- Deterministic Python decides what evidence, mapping, coverage, confidence, and AAS output is
  valid.
- Model tools may request human input. Only `/api/agent/review` and `/api/agent/value` can apply
  trusted human decisions or create human evidence.
- Conversation history and `MiaState` are distinct values in the same LangGraph checkpoint.
- Reusable memory uses LangGraph's SQLite Store and is separate from both thread history and
  generated files.
- Generated data lives under `MIA_WORKSPACE_ROOT/<thread_id>` and is registered in one manifest.

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
targets. The model cannot approve them or assign authoritative confidence.

## Observability and artifacts

Every run and tool action emits a safe `AgentTraceEvent`. These are decision/action summaries,
not private chain-of-thought. Search results, source metadata, evidence, mappings, coverage,
reviews, validation, and AAS output are written as manifest artifacts with hashes and lineage.
The workspace UI can view individual files or download the complete ZIP.

Current limits: event delivery is request/response rather than SSE; local SQLite/filesystem
persistence is single-instance; DDGS results require verification; document extraction and BaSyx
deployment exist but are not model-visible tools; only the pinned template releases are used.
