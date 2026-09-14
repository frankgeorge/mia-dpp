# MIA — deterministic product data to AAS

MIA turns traceable product evidence into a validated Asset Administration
Shell (AAS) environment. The backend is Python. AI can propose unfamiliar
semantic mappings, but Python owns extraction rules, mapping acceptance,
template resolution, AAS compilation, validation, and deployment gates.

The current end-to-end path targets IDTA Digital Nameplate 3.0.1. The same
template loader and compiler are also tested against nested elements from IDTA
Technical Data 2.0.1, so the backend is not a hand-written one-template JSON
generator.

## Run locally

Requirements: Git, Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 20.19+,
and npm. Docker is optional.

```bash
git clone --recurse-submodules git@github.com:frankgeorge/mia-dpp.git
cd mia-dpp
make install
make crawl-setup
make dev
```

Open `http://127.0.0.1:3000`. `Ctrl-C` stops both processes started by
`make dev`.

The deterministic `/api/dpp` capability does not need an API key. The autonomous
workspace does: copy `.env.example` to `.env.local` and set
`OPENROUTER_API_KEY`. Crawl4AI uses locally installed Chromium to render pages.
The model can choose actions and propose bounded mappings, but it cannot invent
authoritative semantic IDs, set confidence, compile AAS JSON, or bypass validation.

With an OpenRouter key, the workspace uses a persistent PydanticAI decision loop:

```text
conversation ↔ autonomous agent ↔ discovery/extraction/mapping/AAS tools
                              ↓
                  typed state + trusted history
```

The chat accepts a company name, product choice, or direct URL. Website acquisition,
fact extraction, mapping assessment, coverage, compilation, and validation remain deterministic.
Semantic proposals are constrained to retained evidence and official requirement IDs.
Trusted PydanticAI message history and typed workflow state are stored server-side in
SQLite for local development.

Run `make help` to see the short command list. The most useful checks are:

```bash
make test       # deterministic Python tests
make check      # standards, lint, types, tests, frontend build, Compose config
make smoke      # build, start, probe, and stop the Docker stack
```

## Deterministic path

```text
source data
  -> EvidenceRecord with provenance
  -> proposed mapping plus an explainable basis and review policy
  -> human-approved MappingSpecification
  -> pinned official IDTA template
  -> aas-core3.0 Environment
  -> AAS metamodel and IDTA template validation
  -> deployable artifact or explicit GapReport
```

Mappings state whether their basis is an exact deterministic rule, semantic
reasoning, or trusted human input. Ambiguity and weak signals require review;
MIA does not present handcrafted scores as statistical confidence.

## Repository map

```text
app/, components/                 Next.js structured-agent interface
backend/src/mia_dpp/mia.py       PydanticAI autonomy and trusted defer/resume
backend/src/mia_dpp/agent/       model-visible tools, state, prompts, dependencies
backend/src/mia_dpp/store.py     sessions, deferrals, reviewed knowledge, artifacts
backend/src/mia_dpp/tools/web/    provenance-aware generic evidence extraction
backend/src/mia_dpp/tools/mapping/
                                  mapping, confidence, coverage, review
backend/src/mia_dpp/aas/          official templates, compiler, validator
backend/src/mia_dpp/domain/       framework-neutral Pydantic concepts
backend/src/mia_dpp/integrations/ vendor-specific adapters
backend/tests/                    deterministic and autonomous-loop tests
standards/idta-submodel-templates/
                                  unmodified, commit-pinned standards data
```

MIA does not copy upstream application source into its own package. `aas-core`
and Crawl4AI are locked Python dependencies behind small MIA boundaries. BaSyx
PDF-to-AAS remains optional, and BaSyx is an external runtime. PydanticAI owns
tool selection and deferred human calls; MIA validates and persists trusted
resume results server-side.

See `docs/agent.md` for the autonomous architecture and
`docs/deterministic-backend.md` for the validation layers.

## Local deployment

```bash
make docker-build
make up
make down
```

The frontend runs on port 3000 and the Python API on port 8000 by default.
Override them with `FRONTEND_PORT`, `BACKEND_PORT`, and `API_URL` when needed.

Current limits are explicit: generic website ingestion recognizes common
schema.org Product data and labelled specification tables. A generated
Crawl4AI site schema must be reviewed and fixture-tested before it is committed
as trusted extraction data. Automatic PDF fact mapping is not yet implemented,
and Digital Nameplate's external
Address Information drop-in is structurally present but reported as not deeply
validated. No OPC-UA, MQTT, PLC, telemetry, or time-series path is included.
