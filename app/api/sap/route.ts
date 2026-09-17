import { createAIClient, MODEL } from "@/lib/ai/client";
import { SAP_SYSTEM } from "@/lib/ai/prompts";
import { PROPOSE_ONLY_TOOLS } from "@/lib/ai/tools";
import { semanticIdFor } from "@/lib/standards/idta";
import { flattenSapResponse } from "@/lib/integrations/sap";
import type { GraphEntry } from "@/lib/standards/types";

export const runtime = "nodejs";
export const maxDuration = 30;

/**
 * SAP OData proxy — fetches material master data from a SAP system and maps
 * it to the IDTA Digital Nameplate submodel.
 *
 * Supports SAP S/4HANA and ECC via OData v2/v4.
 * The client provides their SAP hostname, credentials, and material number.
 */

export async function POST(req: Request) {
  const body = await req.json();
  const {
    sapHost,
    sapClient,
    username,
    password,
    materialNumber,
    graph = [],
  }: {
    sapHost: string;
    sapClient: string;
    username: string;
    password: string;
    materialNumber: string;
    graph: GraphEntry[];
  } = body;

  if (!sapHost || !username || !password || !materialNumber) {
    return Response.json(
      { error: "sapHost, username, password, and materialNumber are required." },
      { status: 400 }
    );
  }

  // ── Fetch from SAP OData ──────────────────────────────────────────────────
  const host = sapHost.replace(/\/$/, "");
  const auth = Buffer.from(`${username}:${password}`).toString("base64");
  const clientParam = sapClient ? `?sap-client=${sapClient}&` : "?";

  // Try S/4HANA OData v4 first, fall back to ECC OData v2
  let sapData: Record<string, string> = {};
  let fetchError = "";

  try {
    // S/4HANA: /sap/opu/odata4/sap/api_material/srvd_a2x/sap/material/0002/Material(MaterialNumber)
    const s4Url = `${host}/sap/opu/odata4/sap/api_material/srvd_a2x/sap/material/0002/Material('${encodeURIComponent(materialNumber)}')${clientParam}$select=Material,MaterialName,BaseUnit,MaterialGroup,CreatedByUser,LastChangedDateTime`;

    const s4Res = await fetch(s4Url, {
      headers: {
        Authorization: `Basic ${auth}`,
        Accept: "application/json",
      },
      signal: AbortSignal.timeout(10_000),
    });

    if (s4Res.ok) {
      const json = await s4Res.json();
      sapData = flattenSapResponse(json);
    } else {
      // ECC OData v2 fallback
      const eccUrl = `${host}/sap/opu/odata/sap/MM_MATERIAL_SRV/MaterialSet('${encodeURIComponent(materialNumber)}')${clientParam}$format=json`;
      const eccRes = await fetch(eccUrl, {
        headers: {
          Authorization: `Basic ${auth}`,
          Accept: "application/json",
        },
        signal: AbortSignal.timeout(10_000),
      });

      if (eccRes.ok) {
        const json = await eccRes.json();
        sapData = flattenSapResponse(json?.d ?? json);
      } else {
        fetchError = `SAP returned HTTP ${eccRes.status}. Check your credentials and material number.`;
      }
    }
  } catch (err: any) {
    fetchError = `Could not reach SAP system: ${err.message}`;
  }

  if (fetchError && Object.keys(sapData).length === 0) {
    return Response.json({ error: fetchError }, { status: 422 });
  }

  // Build context for LLM
  const context = `SAP Material: ${materialNumber}\n\n${Object.entries(sapData)
    .map(([k, v]) => `${k}: ${v}`)
    .join("\n")}`;

  const key = process.env.OPENROUTER_API_KEY;
  if (!key) {
    return Response.json(
      { error: "No AI key configured. Add OPENROUTER_API_KEY to use the SAP connector." },
      { status: 500 }
    );
  }

  const client = createAIClient();

  const graphHint = graph.length
    ? `\n\nIntegration Graph:\n${graph.map((g) => `- ${g.sourceField} → ${g.targetElement}`).join("\n")}`
    : "";

  try {
    const res = await client.chat.completions.create({
      model: MODEL,
      max_tokens: 2000,
      tools: PROPOSE_ONLY_TOOLS,
      tool_choice: "auto",
      messages: [
        { role: "system", content: SAP_SYSTEM + graphHint },
        { role: "user", content: `Map this SAP material data to the DPP:\n\n${context}` },
      ],
    });

    const choice = res.choices[0];
    let reply = choice.message.content ?? "";
    let proposal: any = null;

    for (const call of choice.message.tool_calls ?? []) {
      const fn = (call as any).function as { name: string; arguments: string };
      if (fn.name === "propose_mappings") {
        const args = JSON.parse(fn.arguments);
        proposal = {
          productName: String(args.productName ?? materialNumber),
          mappings: (args.mappings ?? []).map((m: any) => ({
            sourceField: String(m.sourceField ?? "unknown"),
            sourceValue: String(m.sourceValue ?? ""),
            targetElement: String(m.targetElement ?? ""),
            semanticId: semanticIdFor(String(m.targetElement ?? "")),
            confidence: Math.max(0, Math.min(1, Number(m.confidence ?? 0.5))),
            reasoning: String(m.reasoning ?? ""),
          })),
        };
      }
    }

    if (!reply) {
      reply = proposal
        ? `Fetched material ${materialNumber} from SAP and extracted ${proposal.mappings.length} fields. Review the mappings.`
        : `Connected to SAP but could not map material ${materialNumber}. Check the material number.`;
    }

    return Response.json({ reply, proposal, mode: "live", materialNumber });
  } catch (err: any) {
    console.error("SAP agent error", err);
    return Response.json({ error: "Mapping failed after fetching SAP data." }, { status: 500 });
  }
}
