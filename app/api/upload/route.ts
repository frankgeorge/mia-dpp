import { auth } from "@clerk/nextjs/server";
import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 60;

// 20 MB limit
const MAX_BYTES = 20 * 1024 * 1024;

const SUPPORTED = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "text/csv",
  "text/plain",
]);

async function extractPdf(buffer: Buffer): Promise<string> {
  // pdf-parse v1 has a webpack bug where the top-level index.js opens a test file.
  // Importing directly from the lib skips that test runner code.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const pdfParse = require("pdf-parse/lib/pdf-parse") as (buf: Buffer) => Promise<{ text: string }>;
  const result = await pdfParse(buffer);
  return result.text;
}

async function extractExcel(buffer: Buffer): Promise<string> {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const XLSX = await import("xlsx");
  const workbook = XLSX.read(buffer, { type: "buffer" });
  const lines: string[] = [];
  for (const name of workbook.SheetNames) {
    const sheet = workbook.Sheets[name];
    const csv = XLSX.utils.sheet_to_csv(sheet);
    lines.push(`=== Sheet: ${name} ===\n${csv}`);
  }
  return lines.join("\n\n");
}

async function extractDocx(buffer: Buffer): Promise<string> {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const mammoth = await import("mammoth");
  const result = await mammoth.extractRawText({ buffer });
  return result.value;
}

function extractCsv(buffer: Buffer): string {
  return buffer.toString("utf-8");
}

export async function POST(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const formData = await req.formData();
  const file = formData.get("file");

  if (!file || typeof file === "string") {
    return Response.json({ error: "No file provided" }, { status: 400 });
  }

  const mimeType = file.type;
  const fileName = file.name;

  // Check size
  if (file.size > MAX_BYTES) {
    return Response.json(
      { error: `File too large. Maximum size is 20 MB.` },
      { status: 413 }
    );
  }

  // Determine type by mime or extension
  const ext = fileName.split(".").pop()?.toLowerCase() ?? "";
  const isPdf = mimeType === "application/pdf" || ext === "pdf";
  const isExcel =
    mimeType === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" ||
    mimeType === "application/vnd.ms-excel" ||
    ext === "xlsx" ||
    ext === "xls";
  const isDocx =
    mimeType ===
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
    ext === "docx";
  const isCsv = mimeType === "text/csv" || mimeType === "text/plain" || ext === "csv";

  if (!isPdf && !isExcel && !isDocx && !isCsv && !SUPPORTED.has(mimeType)) {
    return Response.json(
      { error: `Unsupported file type: ${mimeType || ext}. Upload a PDF, Excel, CSV, or DOCX file.` },
      { status: 415 }
    );
  }

  try {
    const arrayBuffer = await file.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);

    let text = "";
    let fileType = "document";

    if (isPdf) {
      text = await extractPdf(buffer);
      fileType = "PDF";
    } else if (isExcel) {
      text = await extractExcel(buffer);
      fileType = "Excel spreadsheet";
    } else if (isDocx) {
      text = await extractDocx(buffer);
      fileType = "Word document";
    } else if (isCsv) {
      text = extractCsv(buffer);
      fileType = "CSV";
    }

    // Truncate very long documents to avoid overwhelming the LLM
    const MAX_CHARS = 40_000;
    const truncated = text.length > MAX_CHARS;
    if (truncated) text = text.slice(0, MAX_CHARS);

    const sizeKb = Math.round(file.size / 1024);
    const charCount = text.length;

    return Response.json({
      fileName,
      fileType,
      sizeKb,
      charCount,
      truncated,
      text,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Extraction failed";
    return Response.json({ error: `Could not read file: ${message}` }, { status: 422 });
  }
}
