# MIA — deterministic product data to AAS

MIA turns traceable product evidence into a validated Asset Administration
Shell (AAS) environment. The backend is Python. AI can propose unfamiliar
semantic mappings, but Python owns extraction rules, confidence arithmetic,
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

No API key is needed: manual input and website-to-IDTA mapping are
deterministic. Crawl4AI uses the locally installed Chromium browser to render
submitted product pages.
To let OpenRouter propose mappings, copy `.env.example` to `.env.local` and set
`OPENROUTER_API_KEY`. The model still cannot choose authoritative semantic IDs,
set confidence, compile AAS JSON, or bypass validation.

With an OpenRouter key, the workspace uses a resumable LangGraph workflow:

```text
conversation → website tools → evidence ledger → IDTA coverage
             → semantic proposals → human review → resume
```

The chat can explain MIA and accept a product URL directly. Website acquisition,
fact extraction and coverage remain deterministic. The model sees only retained
evidence and official requirement identifiers, and every additional semantic
mapping pauses for explicit approval or rejection. The MVP checkpointer is
in-memory, so conversation threads survive requests but reset when the Python
process restarts; a durable checkpointer is the next deployment step.

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
  -> proposed mapping plus explainable confidence factors
  -> human-approved MappingSpecification
  -> pinned official IDTA template
  -> aas-core3.0 Environment
  -> AAS metamodel and IDTA template validation
  -> deployable artifact or explicit GapReport
```

Every confidence number is a reproducible evidence score, not a probability.
The interface shows the awarded points and the specific uncertainty behind the
missing points. Previous human decisions can reduce target ambiguity; they do
not prove that a value on a new product is correct.

## Repository map

```text
app/, components/              Next.js interface only
backend/src/mia_dpp/models.py  MIA-owned Pydantic contracts
backend/src/mia_dpp/extraction.py
                               approved website rules and Crawl4AI boundary
backend/src/mia_dpp/website.py product-page text/provenance integration
backend/src/mia_dpp/documents.py
                               optional PDF-to-AAS preprocessing boundary
backend/src/mia_dpp/templates.py
                               verified official-template loader
backend/src/mia_dpp/aas.py     generic compiler and layered validator
backend/src/mia_dpp/pipeline.py
                               deterministic application service
backend/src/mia_dpp/basyx.py   validation-gated BaSyx HTTP adapter
backend/tests/                 unit, contract, and end-to-end tests
standards/idta-submodel-templates/
                               unmodified, commit-pinned standards data
```

MIA does not copy upstream application source into its own package. `aas-core`
and Crawl4AI are locked Python dependencies behind MIA-owned adapters. BaSyx
PDF-to-AAS remains optional, and BaSyx is an external runtime. AASbyLLM and
LangGraph remain reference ideas until a proven service needs them.

See `docs/deterministic-backend.md` for a guided explanation of the code and
the validation layers.

## Local deployment

```bash
make docker-build
make up
make down
```

The frontend runs on port 3000 and the Python API on port 8000 by default.
Override them with `FRONTEND_PORT`, `BACKEND_PORT`, and `API_URL` when needed.

Current limits are explicit: generic website ingestion recognizes common
schema.org Product data and labelled specification tables; unusual sites still
need an approved `SiteAdapterSpec`. Automatic PDF fact mapping is not yet
implemented, browser mapping memory is local, and Digital Nameplate's external
Address Information drop-in is structurally present but reported as not deeply
validated. No OPC-UA, MQTT, PLC, telemetry, or time-series path is included.
