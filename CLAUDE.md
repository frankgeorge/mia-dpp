# MIA — Digital Product Passport Generator

## What this is
MIA (Mittelstand Integration Agent) is an AI-powered web app that turns manufacturer product data into standards-compliant Digital Product Passports (DPPs) for EU ESPR compliance. Targets SME manufacturers (Mittelstand) who cannot afford enterprise DPP platforms.

## Tech stack
- **Framework**: Next.js 14 App Router, TypeScript strict, Tailwind CSS
- **AI**: DeepSeek v3 via OpenRouter (`deepseek/deepseek-chat-v3-0324`)
- **Email**: Resend (free tier — sends from `onboarding@resend.dev`)
- **Hosting**: Vercel (production: https://mia-dpp.vercel.app)
- **State**: localStorage for Integration Graph, in-memory Map for supplier sessions

## Environment variables (all set on Vercel)
- `OPENROUTER_API_KEY` — DeepSeek via OpenRouter
- `RESEND_API_KEY` — Resend email sending
- `NEXT_PUBLIC_BASE_URL` — https://mia-dpp.vercel.app

## Key files
| File | Purpose |
|------|---------|
| `app/workspace/page.tsx` | Main workspace UI — chat, URL scraper, email outreach, mappings panel |
| `app/api/chat/route.ts` | Chat agent — propose_mappings + generate_dpp tools |
| `app/api/scrape/route.ts` | URL scraper endpoint — fetches page, LLM extraction |
| `app/api/email/send/route.ts` | Sends gap request email via Resend |
| `app/api/session/[token]/route.ts` | GET/POST for supplier session state |
| `app/reply/[token]/page.tsx` | Supplier portal — public form for filling missing fields |
| `lib/idta.ts` | NAMEPLATE_ELEMENTS, buildDpp(), demoPropose(), missingRequired() |
| `lib/session.ts` | In-memory supplier session store (replace with DB for production) |
| `lib/scrape.ts` | HTML fetcher + extractor (JSON-LD, spec tables, meta tags) |
| `lib/types.ts` | All TypeScript interfaces |

## The full loop
1. User pastes product URL → `/api/scrape` → HTML fetched server-side → LLM extracts fields → mappings shown
2. Missing required fields → email panel appears → user enters supplier email → `/api/email/send`
3. Supplier receives email with portal link → fills in `/reply/[token]`
4. Workspace polls `/api/session/[token]` every 10s → auto-fills gaps when supplier responds
5. User approves mappings → Generate passport → download AAS JSON

## Demo mode
Runs when no `OPENROUTER_API_KEY` is set. Uses `demoPropose()` regex engine in `lib/idta.ts`. Always works, no API calls.

## Integration Graph
Stored in `localStorage` key `mia.graph.v1`. Every human-approved mapping is saved and reused on future products with +0.22 confidence boost. **Production upgrade needed: move to database.**

## Standards
- IDTA 02006 Digital Nameplate submodel
- AAS (Asset Administration Shell) JSON output format
- EU ESPR compliance target

## What's NOT built yet (next priorities)
1. Auth (Clerk) — no user accounts yet
2. Database (Neon Postgres) — sessions and graph are ephemeral
3. Passport history dashboard
4. File upload (PDF, Excel, CSV)
5. More submodels (Carbon Footprint, Technical Data)
6. QR code + hosted passport permalink
7. SAP OData connector

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
