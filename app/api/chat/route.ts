import OpenAI from "openai";
import { NAMEPLATE_ELEMENTS, semanticIdFor, demoPropose } from "@/lib/idta";
import type { GraphEntry } from "@/lib/types";

export const runtime = "nodejs";
export const maxDuration = 60;

const MODEL = "deepseek/deepseek-chat-v3-0324:free";

const SYSTEM = `You are MIA, an integration agent that turns a manufacturer's messy product data into a standards-compliant Digital Product Passport.

You map source fields onto the IDTA Digital Nameplate submodel. These are the only valid target elements:

${NAMEPLATE_ELEMENTS.map(
  (e) =>
    `- ${e.name}${e.required ? " (required)" : ""} — ${e.hint}`
).join("\n")}

Rules you must follow:
1. When the user describes a product, call propose_mappings once with every field you can identify.
2. Give each mapping an honest confidence between 0 and 1. Be genuinely uncertain when the evidence is weak — a guessed field at 0.55 is far more useful than a false 0.95. Reserve above 0.9 for cases where the label is explicit and unambiguous.
3. sourceField should be the field name as it would appear in a German manufacturer's SAP system (WERKS, MATNR, SERNR, BAUJAHR, NAME1, LAND1) when you can infer it, otherwise a plain descriptive name.
4. Never invent values the user did not provide. Missing data is a gap to report, not to fill.
5. After proposing, tell the user in one or two short sentences what you mapped and what still needs their decision. Do not repeat the whole table back — the interface already shows it.
6. Only call generate_dpp when the user explicitly asks to generate, build, or export the passport.

Be brief and concrete. You are a working tool, not a chatbot.`;

const tools: OpenAI.ChatCompletionTool[] = [
  {
    type: "function",
    function: {
      name: "propose_mappings",
      description:
        "Propose field mappings from the user's product data onto the IDTA Digital Nameplate submodel. Call this once per product description.",
      parameters: {
        type: "object",
        properties: {
          productName: {
            type: "string",
            description: "Short human-readable product name for this passport.",
          },
          mappings: {
            type: "array",
            items: {
              type: "object",
              properties: {
                sourceField: {
                  type: "string",
                  description:
                    "Field name as it would appear in the manufacturer's own system.",
                },
                sourceValue: { type: "string", description: "The value provided by the user." },
                targetElement: {
                  type: "string",
                  description: "Exact name of the target Digital Nameplate element.",
                },
                confidence: {
                  type: "number",
                  description: "Honest confidence from 0 to 1.",
                },
                reasoning: {
                  type: "string",
                  description: "One sentence on why this mapping was chosen.",
                },
              },
              required: [
                "sourceField",
                "sourceValue",
                "targetElement",
                "confidence",
                "reasoning",
              ],
            },
          },
        },
        required: ["productName", "mappings"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "generate_dpp",
      description:
        "Assemble the Digital Product Passport from the mappings the user has approved. Only call when the user asks to generate or export.",
      parameters: {
        type: "object",
        properties: {
          confirm: { type: "boolean", description: "Always true." },
        },
        required: ["confirm"],
      },
    },
  },
];

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
    const client = new OpenAI({
      apiKey: key,
      baseURL: "https://openrouter.ai/api/v1",
      defaultHeaders: {
        "HTTP-Referer": "https://mia-dpp.vercel.app",
        "X-Title": "MIA Digital Product Passport",
      },
    });

    const graphHint = graph.length
      ? `\n\nIntegration Graph — mappings a human already verified on earlier products. Reuse these when the same source field appears again, and raise your confidence accordingly:\n${graph
          .map((g) => `- ${g.sourceField} maps to ${g.targetElement} (verified)`)
          .join("\n")}`
      : "";

    const res = await client.chat.completions.create({
      model: MODEL,
      max_tokens: 2000,
      tools,
      tool_choice: "auto",
      messages: [
        { role: "system", content: SYSTEM + graphHint },
        ...messages.map((m) => ({ role: m.role, content: m.content })),
      ],
    });

    const choice = res.choices[0];
    let reply = choice.message.content ?? "";
    let proposal: any = null;
    let generate = false;

    for (const call of choice.message.tool_calls ?? []) {
      const args = JSON.parse(call.function.arguments);
      if (call.function.name === "propose_mappings") {
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
      if (call.function.name === "generate_dpp") generate = true;
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
