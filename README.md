# MIA — Digital Product Passport Platform

MIA is an AI-powered platform that generates EU ESPR-compliant Digital Product Passports (DPPs) for manufacturers. It maps product data from uploaded documents to official IDTA AAS submodel templates, validates the result, and publishes a public, shareable passport page with a QR code — in minutes.

Live at **[mia-dpp.vercel.app](https://mia-dpp.vercel.app)**

---

## How it works

1. A manufacturer uploads a product datasheet (PDF, Excel, CSV, or DOCX) in the workspace chat.
2. The AI agent extracts product fields and maps them to the relevant IDTA submodel standards (Digital Nameplate, Technical Data, Carbon Footprint, Handover Documentation, etc.).
3. The system flags any required fields that could not be found and prompts the user to provide them.
4. Once all required fields are covered, MIA compiles and validates a standards-compliant AAS JSON artifact.
5. The passport is published at a permanent public URL. A QR code is generated and available to download.

For a detailed breakdown of the agent design — roles, input/output schemas, tool definitions, memory architecture, and evaluation criteria — see [`steps.md`](./steps.md).

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js (App Router), TypeScript, Tailwind CSS |
| Auth | Clerk |
| AI Agent | PydanticAI, OpenRouter (DeepSeek v3.2 default) |
| AAS Compiler | aas-core3.0 (Python), IDTA submodel templates |
| Backend API | FastAPI, Python 3.12, uv |
| Database | Supabase (PostgreSQL via postgres.js) |
| File storage | Supabase Storage |
| PDF generation | PDFKit |
| QR codes | qrcode |
| Email | Resend |
| Deployment | Vercel (Next.js frontend + containerised Python backend) |

---

## Prerequisites

- Git
- Node.js 20.19 or later
- Python 3.12 (exactly — the backend requires `>=3.12,<3.13`)
- [uv](https://docs.astral.sh/uv/) — Python package manager
- npm
- Docker (optional — only needed for the containerised stack)

---

## Local setup

### 1. Clone the repository

```bash
git clone --recurse-submodules git@github.com:frankgeorge/mia-dpp.git
cd mia-dpp
```

The `--recurse-submodules` flag is required: IDTA submodel templates are included as a git submodule under `standards/`.

### 2. Install dependencies

```bash
make install
```

This installs both the Python backend (via uv) and the Next.js frontend (via npm).

### 3. Configure environment variables

```bash
cp .env.example .env.local
```

Open `.env.local` and fill in the required values:

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Yes | Clerk publishable key — [clerk.com](https://clerk.com) |
| `CLERK_SECRET_KEY` | Yes | Clerk secret key |
| `DATABASE_URL` | Yes | PostgreSQL connection string (Supabase transaction pooler URL) |
| `NEXT_PUBLIC_SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Supabase service role key (for file storage) |
| `OPENROUTER_API_KEY` | No | Enables the autonomous AI agent. Without it, the backend runs in deterministic demo mode. |
| `MIA_AGENT_MODEL` | No | Model used by the agent. Defaults to `deepseek/deepseek-v3.2`. |
| `RESEND_API_KEY` | No | Enables email delivery for supplier portal invites. Without it, MIA returns a plain-text draft to copy-paste manually. |
| `NEXT_PUBLIC_BASE_URL` | No | Base URL for supplier portal links. Defaults to `http://localhost:3000` locally. |

### 4. Set up Crawl4AI (web extraction)

```bash
make crawl-setup
```

This installs a local Chromium browser used by Crawl4AI for rendering product pages. Only needed if you plan to use URL-based product ingestion.

### 5. Start the development servers

```bash
make dev
```

This starts both the Next.js frontend (port 3000) and the FastAPI backend (port 8000) concurrently. Open [http://localhost:3000](http://localhost:3000).

Stop both with `Ctrl-C`.

---

## Available make commands

```bash
make install       # Install all frontend and backend dependencies
make crawl-setup   # Install Chromium for Crawl4AI
make dev           # Start frontend + backend in development mode
make test          # Run the deterministic Python test suite
make check         # Full check: lint, types, tests, frontend build, Docker Compose config
make smoke         # Build the Docker stack, start it, probe health endpoints, and stop
make docker-build  # Build the Docker image for the Python backend
make up            # Start the full Docker stack (frontend on 3000, backend on 8000)
make down          # Stop the Docker stack
make help          # Print all available commands
```

---

## Application routes

| Route | Access | Purpose |
|-------|--------|---------|
| `/workspace` | Authenticated | Chat interface — upload documents, interact with MIA, view generated passport |
| `/workspace/assets` | Authenticated | Grid of all passports with QR codes and share links |
| `/workspace/agents` | Authenticated | Audit log of every AI agent execution and extracted fields |
| `/workspace/activity` | Authenticated | Technical trace — agent decisions, mappings, evidence coverage |
| `/workspace/data-sources` | Authenticated | Uploaded documents and ingested data sources |
| `/passport/[id]` | Public | Shareable passport page — no login required, QR-scannable |
| `/reply/[token]` | Public | Supplier portal — suppliers fill missing fields via emailed link |
| `/settings` | Authenticated | Company branding and configuration |

---

## Supported IDTA submodels

| Submodel | Standard | Description |
|----------|----------|-------------|
| Digital Nameplate | IDTA 02006 | Core product identity, manufacturer, and address |
| Technical Data | IDTA 02003 | Specifications, ratings, and technical properties |
| Carbon Footprint | IDTA 02023 | Product carbon footprint (PCF) per GHG Protocol |
| Handover Documentation | IDTA 02004 | Linked datasheets, manuals, and certificates |
| DPP Metadata | IDTA 02099 | Passport governance and compliance metadata |

---

## Project structure

```
app/                        Next.js pages and API routes
  api/                      Backend-for-frontend API routes (auth, passports, uploads)
  passport/[id]/            Public passport page
  workspace/                Authenticated workspace (chat, assets, agents, activity)
components/                 Shared React components
backend/
  src/mia_dpp/
    mia.py                  PydanticAI agent orchestration and defer/resume logic
    agent/                  Model-visible tools, state machine, prompts, dependencies
    aas/                    IDTA template loader, AAS compiler, validator
    tools/                  Web extraction, mapping, coverage, gap analysis
    store.py                Session store, deferrals, reviewed knowledge, artifacts
    domain/                 Framework-neutral Pydantic domain models
    integrations/           Vendor adapters (BaSyx, etc.)
  tests/                    Deterministic and agent-loop test suites
standards/
  idta-submodel-templates/  Unmodified, commit-pinned official IDTA template data (submodule)
lib/                        Shared Next.js utilities (DB client, Supabase client, etc.)
steps.md                    Agent design blueprint — roles, schemas, tools, memory, evaluation
```

---

## Agent design

The full agent blueprint is documented in [`steps.md`](./steps.md). It covers:

- **Step 1** — Agent role, goal, and constraints (what MIA must and must not do)
- **Step 2** — Structured input/output schemas (`DppAgentInput`, `DppAgentOutput`, `MappedField`)
- **Step 3** — System prompt design and hardcoded behavioural rules
- **Step 4** — ReAct reasoning loop and permitted tool set
- **Step 5** — Multi-agent architecture (current single-agent flow and planned planner/specialist split)
- **Step 6** — Memory layers (thread memory, company context, cross-product mapping knowledge, planned RAG)
- **Step 7** — Future voice and vision capabilities
- **Step 8** — Output delivery (public passport page, QR code, AAS JSON download)
- **Step 9** — UI page map and design principles
- **Step 10** — Evaluation criteria, quality metrics, and monitoring

---

## Deployment

The project deploys to Vercel as two services defined in `vercel.json`:

- **frontend** — Next.js App Router, serverless functions
- **backend** — Dockerised FastAPI, container runtime

To deploy to production:

```bash
vercel --prod
```

Set all environment variables listed above in the Vercel project settings before deploying. The `NEXT_PUBLIC_BASE_URL` should be set to your production domain (e.g., `https://mia-dpp.vercel.app`).

---

## Current limitations

- Web ingestion recognises `schema.org/Product` markup and labelled specification tables. Custom site schemas require a reviewed extraction fixture before being committed as trusted.
- Automatic PDF-to-field mapping relies on text extraction. Scanned PDFs without OCR will produce lower field coverage.
- The Digital Nameplate Address Information block is structurally present but not deeply validated against all regional address formats.
- No OPC-UA, MQTT, PLC, or telemetry ingestion path is included in the current release.
