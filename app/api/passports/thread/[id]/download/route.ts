import sql from "@/lib/db";
import PDFDocument from "pdfkit";
import QRCode from "qrcode";

export const runtime = "nodejs";
export const maxDuration = 30;

interface AasElement {
  idShort: string;
  modelType?: string;
  value?: unknown;
  submodelElements?: AasElement[];
  statements?: AasElement[];
}

interface AasSubmodel {
  idShort?: string;
  submodelElements?: AasElement[];
}

const SUBMODEL_LABELS: Record<string, string> = {
  Nameplate: "Digital Nameplate",
  DigitalNameplate: "Digital Nameplate",
  TechnicalData: "Technical Data",
  CarbonFootprint: "Carbon Footprint",
  DPPMetadata: "DPP Metadata",
  HandoverDocumentation: "Handover Documentation",
  MaintenanceInstructions: "Maintenance Instructions",
};

const SUBMODEL_CODES: Record<string, string> = {
  Nameplate: "IDTA 02006",
  DigitalNameplate: "IDTA 02006",
  TechnicalData: "IDTA 02003",
  CarbonFootprint: "IDTA 02023",
  DPPMetadata: "IDTA 02099",
  HandoverDocumentation: "IDTA 02004",
  MaintenanceInstructions: "IDTA 02018",
};

function extractFields(elements: AasElement[]): { label: string; value: string }[] {
  const fields: { label: string; value: string }[] = [];
  for (const el of elements) {
    if (el.modelType === "Property" && el.value != null) {
      const label = el.idShort
        .replace(/([a-z])([A-Z])/g, "$1 $2")
        .replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2")
        .replace(/_/g, " ")
        .replace(/^./, (s) => s.toUpperCase())
        .trim();
      fields.push({ label, value: String(el.value) });
    } else if (el.modelType === "MultiLanguageProperty" && Array.isArray(el.value)) {
      const langs = el.value as Array<{ language: string; text: string }>;
      const en = langs.find((l) => l.language === "en") ?? langs[0];
      if (en?.text) {
        const label = el.idShort.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/^./, (s) => s.toUpperCase()).trim();
        fields.push({ label, value: en.text });
      }
    } else if (el.submodelElements?.length) {
      fields.push(...extractFields(el.submodelElements));
    } else if (el.statements?.length) {
      fields.push(...extractFields(el.statements));
    }
  }
  return fields;
}

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  const rows = await sql`
    SELECT product_name, aas_json, passport_url, product_image_url, qr_code_b64, status, updated_at
    FROM passports WHERE thread_id = ${id} LIMIT 1
  `;

  if (!rows[0]) return Response.json({ error: "Passport not found" }, { status: 404 });

  const { product_name, aas_json, passport_url, qr_code_b64, updated_at } = rows[0];
  if (!aas_json) return Response.json({ error: "No AAS data available" }, { status: 404 });

  const submodels = ((aas_json as Record<string, unknown>).submodels as AasSubmodel[] | undefined) ?? [];
  const passportLink = (passport_url as string | null) ?? `https://mia-dpp.vercel.app/passport/${id}`;

  // Generate QR code PNG buffer
  let qrBuffer: Buffer | null = null;
  try {
    if (qr_code_b64) {
      qrBuffer = Buffer.from(qr_code_b64 as string, "base64");
    } else {
      qrBuffer = await QRCode.toBuffer(passportLink, { width: 120, margin: 1 });
    }
  } catch { /* skip QR if generation fails */ }

  // Build PDF — set up stream BEFORE any drawing or doc.end()
  const doc = new PDFDocument({
    size: "A4",
    margin: 0,
    info: {
      Title: `Digital Product Passport — ${product_name as string}`,
      Author: "MIA Digital Product Passport",
      Subject: "EU ESPR Digital Product Passport",
    },
  });

  // Register stream listeners BEFORE drawing to avoid race conditions
  const pdfPromise = new Promise<Buffer>((resolve, reject) => {
    const chunks: Buffer[] = [];
    doc.on("data", (c: Buffer) => chunks.push(c));
    doc.on("end", () => resolve(Buffer.concat(chunks)));
    doc.on("error", reject);
  });

  const W = 595.28; // A4 width in points
  const MARGIN = 48;
  const CONTENT_W = W - MARGIN * 2;

  // ── Header banner ──────────────────────────────────────────────────────────
  doc.rect(0, 0, W, 72).fill("#0f0f0f");

  // MIA wordmark
  doc.fontSize(15).fillColor("#ffffff").font("Helvetica-Bold").text("MIA", MARGIN, 24, { continued: true });
  doc.fontSize(11).fillColor("#888888").font("Helvetica").text("  ·  Digital Product Passport", { continued: false });

  // Standards badges
  const badgeY = 44;
  const badges = ["IDTA AAS v3.0", "EU ESPR", "GHG Protocol"];
  let bx = MARGIN;
  for (const b of badges) {
    doc.fontSize(8);
    const bw = doc.widthOfString(b) + 16;
    doc.roundedRect(bx, badgeY, bw, 14, 3).fill("#2a2a2a");
    doc.fillColor("#aaaaaa").font("Helvetica").text(b, bx + 8, badgeY + 3);
    bx += bw + 6;
  }

  // ── Product hero section ───────────────────────────────────────────────────
  let y = 96;
  const heroH = qrBuffer ? 120 : 84;

  doc.roundedRect(MARGIN, y, CONTENT_W, heroH, 8).fill("#f8f8f8");
  doc.roundedRect(MARGIN, y, CONTENT_W, heroH, 8).lineWidth(1).stroke("#e8e8e8");

  // Product name & date
  const dateStr = updated_at
    ? new Date(updated_at as string).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })
    : new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });

  doc.fontSize(9).fillColor("#999999").font("Helvetica").text("DIGITAL PRODUCT PASSPORT", MARGIN + 16, y + 16);
  doc.fontSize(17).fillColor("#0f0f0f").font("Helvetica-Bold").text(product_name as string, MARGIN + 16, y + 30, { width: CONTENT_W - 150 });
  doc.fontSize(9).fillColor("#999999").font("Helvetica").text(`Generated: ${dateStr}`, MARGIN + 16, y + 56);
  doc.fontSize(8).fillColor("#3b5bdb").font("Helvetica").text(passportLink, MARGIN + 16, y + 70, { width: CONTENT_W - 150 });

  // QR code (top right of hero)
  if (qrBuffer) {
    try {
      doc.image(qrBuffer, MARGIN + CONTENT_W - 116, y + 10, { width: 100, height: 100 });
    } catch { /* skip */ }
  }

  y += heroH + 20;

  // ── Submodels ──────────────────────────────────────────────────────────────
  for (const sm of submodels) {
    const key = sm.idShort ?? "unknown";
    const label = SUBMODEL_LABELS[key] ?? key.replace(/([a-z])([A-Z])/g, "$1 $2");
    const code = SUBMODEL_CODES[key] ?? "AAS";
    const fields = extractFields(sm.submodelElements ?? []);
    if (fields.length === 0) continue;

    // Section heading bar
    if (y > 720) { doc.addPage(); y = MARGIN; }
    doc.roundedRect(MARGIN, y, CONTENT_W, 26, 5).fill("#0f0f0f");
    doc.fontSize(11).fillColor("#ffffff").font("Helvetica-Bold").text(label, MARGIN + 12, y + 7, { continued: true });
    doc.fontSize(8).fillColor("#888888").font("Helvetica").text(`  ${code}`, { continued: false });
    y += 34;

    // Fields — alternate background rows
    fields.forEach(({ label: fl, value }, idx) => {
      if (y > 760) { doc.addPage(); y = MARGIN; }
      const ROW_H = 18;
      if (idx % 2 === 0) {
        doc.rect(MARGIN, y, CONTENT_W, ROW_H).fill("#fafafa");
      }
      doc.fontSize(9).fillColor("#888888").font("Helvetica").text(fl, MARGIN + 10, y + 5, { width: 180, continued: false });
      doc.fontSize(9).fillColor("#1a1a1a").font("Helvetica").text(value, MARGIN + 200, y + 5, { width: CONTENT_W - 210 });
      doc.moveTo(MARGIN, y + ROW_H).lineTo(MARGIN + CONTENT_W, y + ROW_H).lineWidth(0.5).stroke("#f0f0f0");
      y += ROW_H;
    });
    y += 16;
  }

  // ── Footer ─────────────────────────────────────────────────────────────────
  const PAGE_H = 841.89;
  if (y < PAGE_H - 60) {
    doc.moveTo(MARGIN, PAGE_H - 48).lineTo(W - MARGIN, PAGE_H - 48).lineWidth(0.5).stroke("#e8e8e8");
    doc.fontSize(8).fillColor("#bbbbbb").font("Helvetica")
      .text(`Generated by MIA · mia-dpp.vercel.app · ${new Date().toISOString().slice(0, 10)}`, MARGIN, PAGE_H - 36, { align: "center", width: CONTENT_W });
  }

  // End the document — the pdfPromise resolves when all chunks are collected
  doc.end();
  const pdfBuffer = await pdfPromise;

  const filename = `${String(product_name).replace(/[^a-z0-9]/gi, "_").toLowerCase()}-dpp.pdf`;
  return new Response(new Uint8Array(pdfBuffer), {
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": `attachment; filename="${filename}"`,
    },
  });
}
