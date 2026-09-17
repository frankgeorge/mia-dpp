import { createAIClient, MODEL } from "@/lib/ai/client";
import { SCRAPE_SYSTEM } from "@/lib/ai/prompts";
import { PROPOSE_ONLY_TOOLS } from "@/lib/ai/tools";
import { fetchAndExtract } from "@/lib/integrations/scrape";
import { semanticIdFor, demoPropose } from "@/lib/standards/idta";
import type { GraphEntry } from "@/lib/standards/types";

export const runtime = "nodejs";
export const maxDuration = 30;

export async function POST(req: Request) {
  const body = await req.json();
  const url: string = body.url ?? "";
  const graph: GraphEntry[] = body.graph ?? [];

  if (!url || (!url.startsWith("http") && !url.startsWith("www"))) {
    return Response.json({ error: "Please provide a valid product page URL." }, { status: 400 });
  }

  // ── Fetch and extract ──────────────────────────────────────────────────────
  let page;
  try {
    page = await fetchAndExtract(url);
  } catch (err: any) {
    return Response.json(
      { error: `Could not fetch that URL: ${err.message}` },
      { status: 422 }
    );
  }

  // Build the context block passed to the model
  const structuredSnippet =
    Object.keys(page.structuredData).length > 0
      ? `Structured data (schema.org / JSON-LD):\n${Object.entries(page.structuredData)
          .slice(0, 30)
          .map(([k, v]) => `  ${k}: ${v}`)
          .join("\n")}`
      : "";

  const context = [structuredSnippet, page.text].filter(Boolean).join("\n\n");

  // ── Demo mode ──────────────────────────────────────────────────────────────
  const key = process.env.OPENROUTER_API_KEY;
  if (!key) {
    const { productName, mappings } = demoPropose(context);
    const lifted = applyGraph(mappings, graph);
    const stamped = lifted.map((m, i) => ({
      ...m,
      id: `scrape-${Date.now()}-${i}`,
      status: (m.confidence >= 0.85 ? "auto" : "review") as "auto" | "review",
    }));

    return Response.json({
      reply: `Scraped ${page.title || url} — found ${stamped.length} field${stamped.length === 1 ? "" : "s"} in demo mode. Check the mappings and request any missing values from your supplier.`,
      proposal: { productName, mappings: stamped },
      mode: "demo",
      pageTitle: page.title,
    });
  }

  // ── Live mode ──────────────────────────────────────────────────────────────
  const graphHint = graph.length
    ? `\n\nIntegration Graph — mappings already verified on earlier products:\n${graph
        .map((g) => `- ${g.sourceField} → ${g.targetElement} (verified)`)
        .join("\n")}`
    : "";

  const client = createAIClient();

  try {
    const res = await client.chat.completions.create({
      model: MODEL,
      max_tokens: 2000,
      tools: PROPOSE_ONLY_TOOLS,
      tool_choice: "auto",
      messages: [
        { role: "system", content: SCRAPE_SYSTEM + graphHint },
        {
          role: "user",
          content: `Extract all product fields from this scraped page content:\n\n${context}`,
        },
      ],
    });

    const choice = res.choices[0];
    let reply = choice.message.content ?? "";
    let proposal: any = null;

    for (const call of choice.message.tool_calls ?? []) {
      const fn = (call as any).function as { name: string; arguments: string };
      if (fn.name === "propose_mappings") {
        const args = JSON.parse(fn.arguments);
        const rawMappings = (args.mappings ?? []).map((m: any) => ({
          sourceField: String(m.sourceField ?? "unknown"),
          sourceValue: String(m.sourceValue ?? ""),
          targetElement: String(m.targetElement ?? ""),
          semanticId: semanticIdFor(String(m.targetElement ?? "")),
          confidence: clamp(Number(m.confidence ?? 0.5)),
          reasoning: String(m.reasoning ?? ""),
        }));
        const lifted = applyGraph(rawMappings, graph);
        proposal = {
          productName: String(args.productName ?? "Product"),
          mappings: lifted,
        };
      }
    }

    if (!reply) {
      reply = proposal
        ? `Scraped ${page.title || url} and extracted ${proposal.mappings.length} field${proposal.mappings.length === 1 ? "" : "s"}. Check the mappings and use the email tool for any gaps.`
        : "Fetched the page but couldn't extract product fields. Try describing the product manually in the chat.";
    }

    return Response.json({ reply, proposal, mode: "live", pageTitle: page.title });
  } catch (err: any) {
    console.error("scrape agent error", err);
    return Response.json(
      {
        error:
          "Extraction failed after fetching the page. Check the URL or describe the product manually.",
      },
      { status: 500 }
    );
  }
}

function clamp(n: number): number {
  if (Number.isNaN(n)) return 0.5;
  return Math.max(0, Math.min(1, n));
}

/** Boost confidence for any mapping whose sourceField is already in the graph. */
function applyGraph(
  mappings: any[],
  graph: GraphEntry[]
): any[] {
  return mappings.map((m) => {
    const hit = graph.find(
      (g) => g.sourceField.toLowerCase() === m.sourceField.toLowerCase()
    );
    if (hit && hit.targetElement === m.targetElement) {
      return {
        ...m,
        confidence: Math.min(0.99, m.confidence + 0.22),
        reasoning: `Verified on an earlier product (Integration Graph). ${m.reasoning}`,
        fromGraph: true,
      };
    }
    return m;
  });
}
