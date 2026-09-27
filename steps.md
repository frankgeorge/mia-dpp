# MIA — Agent Design Blueprint

This document defines how the MIA autonomous DPP agent is designed, built, and evaluated.
It follows a structured 10-step framework applied specifically to this project.

---

## Step 1: Define the Agent's Role and Goal

**What will MIA do?**
Read product data from uploaded files (PDF, Excel, CSV, DOCX), extract all relevant product specifications, and map them to the IDTA 02006 Digital Nameplate template to produce a standards-compliant Digital Product Passport (DPP).

**Who is it helping?**
SME manufacturers (Mittelstand) who need to produce EU ESPR-compliant Digital Product Passports but cannot afford enterprise DPP platforms. They have product datasheets but no structured data pipeline.

**What output does it generate?**
- A completed IDTA 02006 DPP JSON
- A QR code linking to a live, public passport page
- A shareable URL that works without a MIA account
- A list of required fields that could not be found, with a request for the user to provide them

**What MIA must NOT do:**
- Search the web to find company information
- Guess or invent product data not present in the source document
- Ask the user for data that IS already in the document
- Show internal technical state (evidence IDs, mapping scores, trace events) to the end user

---

## Step 2: Design Structured Input & Output

**Input schema (what MIA receives):**
```python
class DppAgentInput(BaseModel):
    company_name: str                  # from onboarding, always known
    company_website: str | None        # from onboarding, optional
    document_text: str                 # full extracted text from uploaded file
    document_filename: str             # e.g. "AFRISO_DMU_pressure_EN.pdf"
    document_type: str                 # "PDF" | "Excel" | "CSV" | "DOCX"
    thread_id: str                     # session ID for continuity
    user_message: str | None           # follow-up chat message, if any
```

**Output schema (what MIA returns):**
```python
class DppAgentOutput(BaseModel):
    reply: str                         # plain-language reply shown in chat
    mapped_fields: list[MappedField]   # fields successfully extracted and mapped
    missing_required: list[str]        # IDTA field names still missing
    missing_optional: list[str]        # optional fields not found
    dpp_ready: bool                    # True when all required fields are filled
    dpp_json: dict | None              # full IDTA 02006 JSON when ready
    passport_id: str | None            # DB record ID when saved
```

**Field mapping schema:**
```python
class MappedField(BaseModel):
    idta_field: str        # e.g. "ManufacturerName"
    value: str             # e.g. "AFRISO-EURO-INDEX GmbH"
    source_excerpt: str    # the exact text from the document it came from
    confidence: float      # 0.0 – 1.0
```

**Tools:** Pydantic AI for schema validation and typed agent responses.

---

## Step 3: Tune Behaviour & Add Protocol

**System prompt role:**
MIA is a DPP extraction specialist. It reads manufacturer documents and maps data to the IDTA 02006 Digital Nameplate standard. It never searches the web. It never invents data. It asks only for fields it cannot find.

**Key prompt rules (hardcoded, not overrideable by user):**
1. The manufacturer is always known from onboarding — never search for or ask about it
2. Use ONLY the provided document text as the data source
3. Map to IDTA 02006 fields: ManufacturerName, ManufacturerProductDesignation, ManufacturerArticleNumber, ManufacturerOrderCode, SerialNumber, YearOfConstruction, HardwareVersion, SoftwareVersion, CountryOfOrigin, CompanyLogo, URIOfTheProduct, AddressInformation
4. Required fields must be filled before generating the DPP
5. Optional fields should be noted but must not block DPP generation
6. Reply in plain language — no JSON, no field IDs, no technical jargon in the chat

**Protocol:** MCP (Model Context Protocol) used for standardising tool interfaces and session state.

---

## Step 4: Add Reasoning and Tool Use

**Reasoning framework:** ReAct (Reasoning + Action)
- Agent reasons: "The document mentions 'Güglingen' — this maps to AddressInformation.City"
- Agent acts: maps it, notes confidence, moves to next field

**Tools MIA is allowed to use:**
| Tool | Purpose | When |
|------|---------|------|
| `extract_fields` | Parse document text → structured fields | Always, on document upload |
| `map_to_idta` | Match extracted fields to IDTA 02006 schema | Always, after extraction |
| `check_gaps` | Identify required fields not yet filled | After mapping |
| `ask_user` | Request specific missing required fields | Only when a field is truly missing |
| `generate_dpp` | Build IDTA 02006 JSON from mapped fields | When all required fields are filled |
| `save_passport` | Store DPP to DB, generate QR + URL | After DPP is generated |

**Tools MIA must NOT use:**
- `web_search` — never
- `crawl_url` — never (unless user explicitly provides a product URL)

---

## Step 5: Structure Multi-Agent Logic

MIA uses a **single orchestrator agent** with sequential tool calls — no multi-agent coordination needed for the core DPP flow. The flow is linear:

```
Upload → Extract → Map → Gap Check → (Ask User if gaps) → Generate → Save → QR + URL
```

If the product line expands to multiple submodels (Carbon Footprint, Battery, Machinery), a **Planner agent** will be introduced to:
1. Identify which IDTA submodels apply to the product
2. Spawn a specialist extractor agent per submodel
3. Merge results into a multi-submodel DPP

**Future tools:** LangGraph for orchestrating multi-submodel flows.

---

## Step 6: Add Memory and Long-Term Context

**Session memory (per passport):**
- Thread ID ties together all messages, uploaded docs, and mappings for one product
- Stored in SQLite (local) or Neon Postgres (Vercel)

**Company memory (across passports):**
- Company name, website, description stored in localStorage after onboarding
- Prepended to every agent call so MIA always knows who it's working for

**Knowledge graph (cross-product learning):**
- Every confirmed field mapping is saved (source label → IDTA field)
- Future uploads from the same manufacturer reuse trusted mappings with high confidence
- Stored in DB table `mapping_knowledge`

**Next iteration — RAG (Retrieval-Augmented Generation):**
AFRISO alone has ~1,000 products. Once the initial single-document flow is working, RAG is the next priority for two reasons:
1. **Large catalogues** — a 300-page AFRISO catalogue is too large for a single LLM context window. RAG chunks the document, embeds each chunk, and retrieves only the pages relevant to the specific product being passported.
2. **Smart mapping reuse** — instead of exact-match lookup in `mapping_knowledge`, use vector similarity so "Betriebsdruck" (German) automatically matches "operating pressure" across product families.

**Planned stack:** Supabase pgvector (already have Supabase DB) + LangChain document loaders for chunking. Embed with `text-embedding-3-small` via OpenRouter.

**Future:** Additional vector embeddings (FAISS) for offline/local scenarios.

---

## Step 7: Voice and Vision (Future)

Not in scope for v1. Potential future additions:
- **Vision:** GPT-4o or LLaMA Vision to read scanned PDFs, wiring diagrams, and product images
- **Voice:** ElevenLabs for accessibility — user describes product verbally, MIA transcribes and maps

---

## Step 8: Deliver the Output

**Primary output:** Public passport page at `https://mia-dpp.vercel.app/passport/[id]`
- Human-readable product data display
- QR code (downloadable)
- Shareable URL (works without MIA account)
- SHA-256 verification hash

**Secondary output:** IDTA 02006 JSON (downloadable from Assets page)

**Format:** Validated against IDTA 02006 schema before saving. Invalid passports are not published.

---

## Step 9: Wrap in a UI

**Frontend:** Next.js 16 App Router (TypeScript, Tailwind CSS)

**User-facing pages:**
| Route | Purpose |
|-------|---------|
| `/workspace` | Chat interface — upload file, answer MIA's questions, see QR + link |
| `/workspace/assets` | Grid of all generated passports with QR codes and share links |
| `/workspace/activity?thread=xxx` | Technical view — agent trace, mappings, evidence, coverage (for power users) |
| `/passport/[id]` | Public passport page — shareable, no login required |
| `/settings` | Company branding, SAP connector config |
| `/reply/[token]` | Supplier portal — supplier fills missing fields via email link |

**Design principle:** The main workspace shows only what a non-technical manufacturer needs to see. All agent internals are on the activity page.

---

## Step 10: Evaluate and Monitor

**Test prompts to run on every deploy:**
1. Upload AFRISO DMU pressure gauge PDF → expect ManufacturerName, AddressInformation mapped
2. Upload a blank PDF → expect MIA to ask for product name and specs
3. Upload an Excel BOM → expect table rows parsed and fields extracted
4. Type product description in chat → expect mapping without web search

**Quality metrics:**
| Metric | Target |
|--------|--------|
| Required fields filled from PDF | ≥ 70% for a good datasheet |
| False mappings (wrong field) | < 5% |
| Time to DPP from upload | < 30 seconds |
| User questions asked per passport | ≤ 3 |

**Monitoring:**
- Vercel function logs for errors
- DB `passports` table for completion rate (draft vs deployed)
- DB `mapping_knowledge` table for confirmation vs correction ratio

---

## Current Status

| Step | Status | Notes |
|------|--------|-------|
| 1 — Role & Goal | ✅ Defined | See above |
| 2 — Input/Output Schema | 🔄 In progress | Pydantic schemas exist in backend; need gap/missing field output |
| 3 — System Prompt & Protocol | 🔄 In progress | Company context prepended; web search suppression being enforced |
| 4 — Reasoning & Tools | 🔄 In progress | Backend has tools; need to remove web_search from upload flow |
| 5 — Multi-agent | ⏳ Future | Single agent for now |
| 6 — Memory | ✅ Done | Thread memory + company localStorage + mapping_knowledge DB |
| 7 — Voice/Vision | ⏳ Future | |
| 8 — Output delivery | ✅ Done | Public passport page + QR code + shareable URL |
| 9 — UI | ✅ Done | Workspace, Assets, Activity, Passport, Supplier portal |
| 10 — Evaluate & Monitor | ⏳ Pending | Test suite needed |
