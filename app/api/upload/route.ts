import { createAIClient, MODEL } from "@/lib/ai/client";
import { UPLOAD_SYSTEM } from "@/lib/ai/prompts";
import { PROPOSE_ONLY_TOOLS } from "@/lib/ai/tools";
import { semanticIdFor, demoPropose } from "@/lib/standards/idta";
import type { GraphEntry } from "@/lib/standards/types";
import * as XLSX from "xlsx";

export const runtime = "nodejs";
export const maxDuration = 60;

export async function POST(req: Request) {
  const formData = await req.formData();
  const file = formData.get("file") as File | null;
  const graphRaw = formData.get("graph") as string | null;
  const graph: GraphEntry[] = graphRaw ? JSON.parse(graphRaw) : [];

  if (!file) {
    return Response.json({ error: "No file provided." }, { status: 400 });
  }

  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  let extractedText = "";
  let fileName = file.name;

  try {
    if (ext === "pdf") {
      extractedText = await extractPdf(file);
    } else if (ext === "xlsx" || ext === "xls" || ext === "csv") {
      extractedText = await extractSpreadsheet(file, ext);
    } else {
      return Response.json(
        { error: "Unsupported file type. Please upload a PDF, Excel (.xlsx/.xls), or CSV file." },
        { status: 400 }
      );
    }
  } catch (err: any) {
    return Response.json(
      { error: `Could not parse file: ${err.message}` },
      { status: 422 }
    );
  }

  if (!extractedText.trim()) {
    return Response.json(
      { error: "The file appears to be empty or could not be read." },
      { status: 422 }
    );
  }

  // Cap at 8000 chars
  const context = extractedText.slice(0, 8000);

  // Demo mode
  const key = process.env.OPENROUTER_API_KEY;
  if (!key) {
    const { productName, mappings } = demoPropose(context);
    const stamped = mappings.map((m, i) => ({
      ...m,
      id: `upload-${Date.now()}-${i}`,
      status: (m.confidence >= 0.85 ? "auto" : "review") as "auto" | "review",
    }));
    return Response.json({
      reply: `Parsed ${fileName} and found ${stamped.length} field${stamped.length === 1 ? "" : "s"} in demo mode. Review the mappings and fill any gaps.`,
      proposal: { productName, mappings: stamped },
      mode: "demo",
      fileName,
    });
  }

  // Live mode
  const graphHint = graph.length
    ? `\n\nIntegration Graph (verified mappings to reuse):\n${graph
        .map((g) => `- ${g.sourceField} → ${g.targetElement}`)
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
        { role: "system", content: UPLOAD_SYSTEM + graphHint },
        {
          role: "user",
          content: `Extract all product fields from this uploaded file (${fileName}):\n\n${context}`,
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
        proposal = {
          productName: String(args.productName ?? "Product"),
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
        ? `Parsed ${fileName} and extracted ${proposal.mappings.length} field${proposal.mappings.length === 1 ? "" : "s"}. Check the mappings and request any gaps from your supplier.`
        : `Parsed ${fileName} but could not identify product fields. Try a different file or describe the product manually.`;
    }

    return Response.json({ reply, proposal, mode: "live", fileName });
  } catch (err: any) {
    console.error("upload agent error", err);
    return Response.json({ error: "Extraction failed. Try again or describe the product manually." }, { status: 500 });
  }
}

// ── File parsers ────────────────────────────────────────────────────────────

async function extractPdf(file: File): Promise<string> {
  const buffer = Buffer.from(await file.arrayBuffer());
  // Dynamically import pdf-parse to avoid issues with Next.js bundling
  const pdfModule = await import("pdf-parse");
  const pdfParse = (pdfModule as any).default ?? pdfModule;
  const data = await pdfParse(buffer);
  return data.text;
}

async function extractSpreadsheet(file: File, ext: string): Promise<string> {
  const buffer = Buffer.from(await file.arrayBuffer());

  if (ext === "csv") {
    // CSV: decode as text directly
    const text = new TextDecoder().decode(buffer);
    return csvToText(text);
  }

  // Excel
  const workbook = XLSX.read(buffer, { type: "buffer" });
  const lines: string[] = [];

  for (const sheetName of workbook.SheetNames) {
    const sheet = workbook.Sheets[sheetName];
    const rows: string[][] = XLSX.utils.sheet_to_json(sheet, { header: 1, defval: "" });

    lines.push(`Sheet: ${sheetName}`);
    for (const row of rows.slice(0, 100)) {
      // Take first 100 rows
      const cells = (row as any[]).map((c) => String(c ?? "").trim()).filter(Boolean);
      if (cells.length > 0) lines.push(cells.join(" | "));
    }
  }

  return lines.join("\n");
}

function csvToText(csv: string): string {
  return csv
    .split("\n")
    .slice(0, 100)
    .map((row) =>
      row
        .split(",")
        .map((c) => c.replace(/^"|"$/g, "").trim())
        .join(" | ")
    )
    .join("\n");
}
