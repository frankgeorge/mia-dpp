# MIA — Mittelstand Integration Agent

Turns a manufacturer's messy product data into a standards-compliant Digital
Product Passport, mapped onto the IDTA Digital Nameplate submodel. Agents
propose every mapping with a confidence score; a human approves anything the
system isn't sure about.

Built for the LEVEL3 AI Engineering track.

---

## Deploy to Vercel

**Option A — from GitHub (recommended)**

```bash
git init
git add .
git commit -m "MIA initial"
git branch -M main
git remote add origin https://github.com/<you>/mia-dpp.git
git push -u origin main
```

Then on [vercel.com/new](https://vercel.com/new): import the repo and press
Deploy. Next.js is detected automatically — no build settings to change.

**Option B — from the CLI**

```bash
npm i -g vercel
vercel
```

### Environment variable

| Name | Required | Effect |
|---|---|---|
| `ANTHROPIC_API_KEY` | No | With it, the chat runs on a real Claude agent with tool calling. Without it, the app runs a deterministic local agent and shows a **Demo mode** badge. |

Set it in Vercel under **Settings → Environment Variables**, then redeploy.

The app is fully demoable with no key set — useful if you're presenting on
someone else's network or don't want to burn credits during a pitch.

---

## Run locally

```bash
npm install
cp .env.example .env.local   # optional, add your key
npm run dev                  # http://localhost:3000
```

---

## What's in it

```
app/
  page.tsx              Landing page
  workspace/page.tsx    The application
  api/chat/route.ts     Agent endpoint (Claude tool calling + demo fallback)
components/
  Nameplate.tsx         Hero: an etched plate resolving into mapped fields
  MappingRow.tsx        One proposed mapping + its approval gate
  DppView.tsx           Generated passport, preview and download
lib/
  idta.ts               Digital Nameplate submodel, DPP builder, demo agent
  types.ts              Shared types
```

### Core features

- **Chat-driven passport creation.** Describe a product in plain language; the
  agent extracts fields and proposes mappings.
- **Confidence scoring.** Every mapping carries a score. Above 0.85 clears
  automatically; below it stops for a person.
- **Approval gates.** Approve, re-target, or discard any mapping. Nothing
  reaches the passport without passing this.
- **Gap reporting.** Missing required elements are listed explicitly. The agent
  never invents values it wasn't given.
- **Integration Graph.** Every approval and correction is written back and
  reused on the next product, raising confidence on fields you've already
  verified. Persists in the browser across sessions.
- **AAS-shaped export.** Downloads a Digital Nameplate submodel as JSON, with
  confidence and source field preserved as qualifiers for audit.

---

## Demo script (about 3 minutes)

1. Land on `/`, point at the nameplate — the same plate before and after mapping.
2. **Try for free** → workspace.
3. Press the **Pressure gauge** sample. Eight fields map; note the confidence
   bars and that one sits below the line.
4. Open **Change target** on the low-confidence row, correct it, approve.
5. Switch to the **Integration Graph** tab — your decision is now stored.
6. Press the **Sparse data** sample. The field you just verified comes back
   marked *From Integration Graph* at much higher confidence. **This is the
   whole thesis: the second passport costs less human attention than the first.**
7. **Generate passport** → preview, then **Download package**.


