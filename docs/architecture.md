# How to read MIA

MIA separates autonomous decisions from deterministic product-data processing. Read the backend
in this order:

1. `mia_dpp/main.py` — the production ASGI entrypoint.
2. `mia_dpp/bootstrap.py` — explicit construction of concrete dependencies.
3. `mia_dpp/agent/graph.py` — the small LangGraph checkpoint/interrupt lifecycle.
4. `mia_dpp/agent/brain.py` — the single PydanticAI autonomous decision loop.
5. `mia_dpp/agent/models.py` — trusted typed job state and safe activity events.
6. `mia_dpp/agent/tools.py` — the small model-visible action surface.
7. `mia_dpp/workspace/` — manifest, lineage, artifact viewing, and export.
8. `mia_dpp/tools/mapping/` — deterministic evidence-to-target mapping and coverage.
9. `mia_dpp/aas/` — official templates, requirement inventory, compilation, and validation.
10. `mia_dpp/integrations/` — vendor-specific Crawl4AI, DDGS, PDF, and BaSyx code.

The architectural vocabulary is deliberately narrow:

- **Agent** chooses actions and maintains the plan/act/observe loop.
- **LLM** reasons; it does not become authoritative merely because it selected a tool.
- **Tool** acts on or retrieves from a source and stops at a stable MIA boundary.
- **Integration** implements a boundary with vendor-specific technology.
- **Domain** contains stable framework-neutral data concepts.
- **Mapping** deterministically interprets evidence against target requirements.
- **AAS** constructs and validates the target using official template metadata.

The central data direction is evidence first:

```text
source → evidence → deterministic mapping → bounded semantic proposal → review → AAS validation
```

Web extraction never assigns authoritative AAS semantics, and unmatched evidence is retained.

The document extraction capability and BaSyx deployment integration are implemented and tested,
but neither is currently exposed to MIA agent.
