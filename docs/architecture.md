# How to read MIA

MIA separates agent orchestration from deterministic product-data processing. Read the
backend in this order:

1. `mia_dpp/main.py` — the production ASGI entrypoint.
2. `mia_dpp/bootstrap.py` — explicit construction of concrete dependencies.
3. `mia_dpp/agent/graph.py` — the LangGraph topology and interrupt/resume boundary.
4. `mia_dpp/agent/nodes/` — intake, web extraction, resolution, review, and completion steps.
5. `mia_dpp/llm/chat.py` — conversational reasoning.
6. `mia_dpp/llm/semantic.py` — conservative semantic proposals for human review.
7. `mia_dpp/tools/` — source capabilities, with web extraction used by the current agent.
8. `mia_dpp/resolution/` — deterministic evidence-to-target mapping and coverage.
9. `mia_dpp/aas/` — official templates, requirement inventory, compilation, and validation.
10. `mia_dpp/integrations/` — vendor-specific OpenRouter, Crawl4AI, and BaSyx code.

The architectural vocabulary is deliberately narrow:

- **Agent** orchestrates state, choices, interruptions, and resumptions.
- **LLM** reasons through a named role; it is not itself a tool.
- **Tool** acts on or retrieves from a source and stops at a stable MIA boundary.
- **Integration** implements a boundary with vendor-specific technology.
- **Domain** contains stable framework-neutral data concepts.
- **Resolution** deterministically interprets evidence against target requirements.
- **AAS** constructs and validates the target using official template metadata.

The central data direction is evidence first:

```text
source → evidence → resolution → human review → approved mapping → AAS validation
```

Web extraction never assigns authoritative AAS semantics, and unmatched evidence is retained.

The document extraction capability and BaSyx deployment integration are implemented and tested,
but neither is currently connected to the LangGraph workflow.
