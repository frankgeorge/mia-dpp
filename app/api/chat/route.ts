import { createAIClient, MODEL } from "@/lib/ai/client";
import { CHAT_SYSTEM } from "@/lib/ai/prompts";
import { CHAT_TOOLS } from "@/lib/ai/tools";
import { semanticIdFor, demoPropose } from "@/lib/standards/idta";
import type { GraphEntry } from "@/lib/standards/types";

export const runtime = "nodejs";
export const maxDuration = 60;

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const messages: { role: "user" | "assistant"; content: string }[] =
      body.messages ?? [];
    const graph: GraphEntry[] = body.graph ?? [];

    const last = messages[messages.length - 1]?.content ?? "";
    const key = process.env.OPENROUTER_API_KEY;

    /* ---------- Demo mode: no API key configured ---------- */
    if (!key) {
      return Response.json(demoTurn(last, graph));
    }

    /* ---------- Live mode via OpenRouter → DeepSeek ---------- */
    const client = createAIClient();

    const graphHint = graph.length
      ? `\n\nIntegration Graph — mappings a human already verified on earlier products. Reuse these when the same source field appears again, and raise your confidence accordingly:\n${graph
          .map((g) => `- ${g.sourceField} maps to ${g.targetElement} (verified)`)
          .join("\n")}`
      : "";

    const res = await client.chat.completions.create({
      model: MODEL,
      max_tokens: 2000,
      tools: CHAT_TOOLS,
      tool_choice: "auto",
      messages: [
        { role: "system", content: CHAT_SYSTEM + graphHint },
        ...messages.map((m) => ({ role: m.role, content: m.content })),
      ],
    });

    const choice = res.choices[0];
    let reply = choice.message.content ?? "";
    let proposal: any = null;
    let generate = false;

    for (const call of choice.message.tool_calls ?? []) {
      const fn = (call as any).function as { name: string; arguments: string };
      const args = JSON.parse(fn.arguments);
      if (fn.name === "propose_mappings") {
        proposal = {
          productName: args.productName,
          mappings: (args.mappings ?? []).map((m: any) => ({
            sourceField: String(m.sourceField ?? "unknown"),
            sourceValue: String(m.sourceValue ?? ""),
            targetElement: String(m.targetElement ?? ""),
            semanticId: semanticIdFor(String(m.targetElement ?? "")),
            confidence: clamp(Number(m.confidence ?? 0.5)),
            reasoning: String(m.reasoning ?? ""),
          })),
        };
      }
      if (fn.name === "generate_dpp") generate = true;
    }

    if (!reply) {
      reply = proposal
        ? "Mapped what I could from that. Anything below the confidence line is waiting on your decision."
        : generate
        ? "Building the passport from your approved mappings."
        : "Tell me about the product and I'll map it.";
    }

    return Response.json({ reply, proposal, generate, mode: "live" });
  } catch (err: any) {
    console.error("chat error", err);
    return Response.json(
      {
        reply:
          "That request didn't reach the model. Check the OPENROUTER_API_KEY setting and try again — the rest of the workspace still works in demo mode.",
        proposal: null,
        generate: false,
        mode: "error",
      },
      { status: 200 }
    );
  }
}

function clamp(n: number) {
  if (Number.isNaN(n)) return 0.5;
  return Math.max(0, Math.min(1, n));
}

/* Deterministic local agent so the demo works with no key set. */
function demoTurn(text: string, graph: GraphEntry[]) {
  const wantsGenerate =
    /\b(generate|build|create|export|make)\b.*\b(dpp|passport|package|aasx)\b/i.test(
      text
    ) || /^(generate|export|build it|do it|yes)\b/i.test(text.trim());

  const looksLikeProduct =
    text.trim().length > 12 &&
    /\d|model|typ|serial|ip\d|bar|product|gauge|clamp|table|sensor|valve/i.test(text);

  if (wantsGenerate && !looksLikeProduct) {
    return {
      reply: "Building the passport from your approved mappings.",
      proposal: null,
      generate: true,
      mode: "demo",
    };
  }

  if (!looksLikeProduct) {
    return {
      reply:
        "Describe the product and I'll map it — manufacturer, model, serial number, year, plant, and any technical values you have. Or press one of the sample products above.",
      proposal: null,
      generate: false,
      mode: "demo",
    };
  }

  const { productName, mappings } = demoPropose(text);

  const lifted = mappings.map((m) => {
    const hit = graph.find(
      (g) => g.sourceField.toLowerCase() === m.sourceField.toLowerCase()
    );
    if (hit && hit.targetElement === m.targetElement) {
      return {
        ...m,
        confidence: Math.min(0.99, m.confidence + 0.22),
        reasoning: `Verified on an earlier product, so this is reused from the Integration Graph. ${m.reasoning}`,
        fromGraph: true,
      };
    }
    return m;
  });

  const low = lifted.filter((m) => m.confidence < 0.85).length;
  const reused = lifted.filter((m: any) => m.fromGraph).length;

  let reply = `Found ${lifted.length} field${lifted.length === 1 ? "" : "s"} in that description.`;
  if (reused) reply += ` ${reused} came straight from the Integration Graph.`;
  reply += low
    ? ` ${low} ${low === 1 ? "is" : "are"} below the confidence line and ${low === 1 ? "needs" : "need"} your decision.`
    : " All of them cleared the confidence line.";

  return {
    reply,
    proposal: { productName, mappings: lifted },
    generate: false,
    mode: "demo",
  };
}
