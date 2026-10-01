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

const SUBMODEL_ACCENT: Record<string, string> = {
  Nameplate: "#1a1a1a",
  DigitalNameplate: "#1a1a1a",
  TechnicalData: "#1d4ed8",
  CarbonFootprint: "#15803d",
  DPPMetadata: "#7c3aed",
  HandoverDocumentation: "#b45309",
  MaintenanceInstructions: "#be123c",
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
        const label = el.idShort
          .replace(/([a-z])([A-Z])/g, "$1 $2")
          .replace(/^./, (s) => s.toUpperCase())
          .trim();
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

async function fetchImageBuffer(url: string): Promise<Buffer | null> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    const res = await fetch(url, { signal: controller.signal });
    clearTimeout(timeout);
    if (!res.ok) return null;
    const ab = await res.arrayBuffer();
    return Buffer.from(ab);
  } catch {
    return null;
  }
}

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  const rows = await sql`
    SELECT product_name, aas_json, passport_url, product_image_url, qr_code_b64, status, updated_at
    FROM passports WHERE thread_id = ${id} LIMIT 1
  `;

  if (!rows[0]) return Response.json({ error: "Passport not found" }, { status: 404 });

  const { product_name, aas_json, passport_url, product_image_url, qr_code_b64, updated_at } = rows[0];
  if (!aas_json) return Response.json({ error: "No AAS data available" }, { status: 404 });

  const submodels = ((aas_json as Record<string, unknown>).submodels as AasSubmodel[] | undefined) ?? [];
  const passportLink = (passport_url as string | null) ?? `https://mia-dpp.vercel.app/passport/${id}`;

  // Fetch product image and QR code in parallel
  const [productImgBuffer, qrBuffer] = await Promise.all([
    product_image_url ? fetchImageBuffer(product_image_url as string) : Promise.resolve(null),
    (async () => {
      try {
        if (qr_code_b64) return Buffer.from(qr_code_b64 as string, "base64");
        return await QRCode.toBuffer(passportLink, { width: 128, margin: 1 });
      } catch { return null; }
    })(),
  ]);

  // ─── PDF layout constants ────────────────────────────────────────────────
  const W = 595.28;   // A4 width pts
  const H = 841.89;   // A4 height pts
  const MARGIN = 44;
  const CW = W - MARGIN * 2;   // content width

  const doc = new PDFDocument({ size: "A4", margin: 0, info: {
    Title: `Digital Product Passport — ${product_name as string}`,
    Author: "MIA",
    Subject: "EU ESPR Digital Product Passport",
  }});

  // Register listeners BEFORE any drawing
  const pdfPromise = new Promise<Buffer>((resolve, reject) => {
    const chunks: Buffer[] = [];
    doc.on("data", (c: Buffer) => chunks.push(c));
    doc.on("end", () => resolve(Buffer.concat(chunks)));
    doc.on("error", reject);
  });

  // ─── Header bar ──────────────────────────────────────────────────────────
  doc.rect(0, 0, W, 64).fill("#0f0f0f");

  doc.fontSize(16).fillColor("#ffffff").font("Helvetica-Bold")
    .text("MIA", MARGIN, 20, { continued: true });
  doc.fontSize(10).fillColor("#888888").font("Helvetica")
    .text("  ·  Digital Product Passport", { continued: false });

  // Standards badges
  const badges = ["IDTA AAS v3.0", "EU ESPR", "GHG Protocol"];
  let bx = MARGIN;
  const badgeY = 40;
  doc.fontSize(7.5);
  for (const b of badges) {
    const bw = doc.widthOfString(b) + 14;
    doc.roundedRect(bx, badgeY, bw, 13, 2).fill("#2a2a2a");
    doc.fillColor("#aaaaaa").font("Helvetica").text(b, bx + 7, badgeY + 3);
    bx += bw + 5;
  }

  // ─── Hero card ────────────────────────────────────────────────────────────
  let y = 80;
  const HERO_H = 110;

  doc.roundedRect(MARGIN, y, CW, HERO_H, 6).fill("#f9f9f9");
  doc.roundedRect(MARGIN, y, CW, HERO_H, 6).lineWidth(0.75).stroke("#e8e8e8");

  const IMG_SIZE = 80;
  const IMG_X = MARGIN + 14;
  const IMG_Y = y + 15;

  // Product image
  if (productImgBuffer) {
    try {
      // Draw white rounded square behind image
      doc.roundedRect(IMG_X - 2, IMG_Y - 2, IMG_SIZE + 4, IMG_SIZE + 4, 4).fill("#ffffff");
      doc.roundedRect(IMG_X - 2, IMG_Y - 2, IMG_SIZE + 4, IMG_SIZE + 4, 4).lineWidth(0.5).stroke("#e8e8e8");
      doc.image(productImgBuffer, IMG_X, IMG_Y, { fit: [IMG_SIZE, IMG_SIZE], align: "center", valign: "center" });
    } catch { /* skip image if format unsupported */ }
  }

  // Product info (shift right if image present)
  const textX = productImgBuffer ? IMG_X + IMG_SIZE + 14 : MARGIN + 14;
  const textMaxW = CW - (textX - MARGIN) - (qrBuffer ? 110 : 20);

  const dateStr = updated_at
    ? new Date(updated_at as string).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })
    : new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });

  doc.fontSize(8).fillColor("#999999").font("Helvetica")
    .text("DIGITAL PRODUCT PASSPORT", textX, y + 14);
  doc.fontSize(15).fillColor("#0f0f0f").font("Helvetica-Bold")
    .text(product_name as string, textX, y + 27, { width: textMaxW, lineBreak: false });

  // Extract manufacturer for subtitle
  let manufacturer = "";
  for (const sm of submodels) {
    const key = sm.idShort ?? "";
    if (key === "Nameplate" || key === "DigitalNameplate" || key === "digital_nameplate") {
      for (const el of sm.submodelElements ?? []) {
        if ((el.idShort === "ManufacturerName" || el.idShort === "Manufacturer Name") && el.value) {
          manufacturer = String(el.value);
        }
        if (!manufacturer && el.modelType === "MultiLanguageProperty" && el.idShort.toLowerCase().includes("manufacturer")) {
          const langs = el.value as Array<{ language: string; text: string }> | undefined;
          const en = langs?.find((l) => l.language === "en") ?? langs?.[0];
          if (en?.text) manufacturer = en.text;
        }
      }
    }
    if (manufacturer) break;
  }

  if (manufacturer) {
    doc.fontSize(9).fillColor("#666666").font("Helvetica")
      .text(manufacturer, textX, y + 48, { width: textMaxW });
  }

  doc.fontSize(8).fillColor("#bbbbbb").font("Helvetica")
    .text(`Generated: ${dateStr}`, textX, y + 62);
  doc.fontSize(7.5).fillColor("#3b5bdb").font("Helvetica")
    .text(passportLink, textX, y + 74, { width: textMaxW });

  // QR code — top right of hero
  if (qrBuffer) {
    try {
      doc.image(qrBuffer, MARGIN + CW - 108, y + 8, { width: 94, height: 94 });
    } catch { /* skip */ }
  }

  y += HERO_H + 18;

  // ─── Submodels ────────────────────────────────────────────────────────────
  for (const sm of submodels) {
    const key = sm.idShort ?? "unknown";
    const label = SUBMODEL_LABELS[key] ?? key.replace(/([a-z])([A-Z])/g, "$1 $2");
    const code = SUBMODEL_CODES[key] ?? "AAS";
    const accent = SUBMODEL_ACCENT[key] ?? "#1a1a1a";
    const fields = extractFields(sm.submodelElements ?? []);
    if (fields.length === 0) continue;

    // Page break check — leave room for heading + at least 2 rows
    if (y > H - 80) { doc.addPage(); y = MARGIN; }

    // Section heading
    doc.roundedRect(MARGIN, y, CW, 24, 4).fill(accent);
    doc.fontSize(10).fillColor("#ffffff").font("Helvetica-Bold")
      .text(label, MARGIN + 12, y + 7, { continued: true });
    doc.fontSize(7.5).fillColor("rgba(255,255,255,0.6)").font("Helvetica")
      .text(`  ${code}`, { continued: false });
    y += 30;

    // Field rows
    fields.forEach(({ label: fl, value }, idx) => {
      const ROW_H = 17;
      // Page break mid-submodel
      if (y > H - 36) { doc.addPage(); y = MARGIN; }

      if (idx % 2 === 0) {
        doc.rect(MARGIN, y, CW, ROW_H).fill("#f7f7f7");
      }

      // Label
      doc.fontSize(8.5).fillColor("#888888").font("Helvetica")
        .text(fl, MARGIN + 10, y + 4, { width: 185, continued: false });

      // Value — truncate very long values
      const displayValue = value.length > 120 ? value.slice(0, 117) + "…" : value;
      doc.fontSize(8.5).fillColor("#1a1a1a").font("Helvetica")
        .text(displayValue, MARGIN + 202, y + 4, { width: CW - 210, continued: false });

      // Row divider
      doc.moveTo(MARGIN, y + ROW_H)
        .lineTo(MARGIN + CW, y + ROW_H)
        .lineWidth(0.4).stroke("#eeeeee");

      y += ROW_H;
    });

    y += 14;
  }

  // ─── Footer ───────────────────────────────────────────────────────────────
  // Draw footer on the last page only if there's room
  if (y < H - 50) {
    doc.moveTo(MARGIN, H - 44).lineTo(W - MARGIN, H - 44).lineWidth(0.5).stroke("#e0e0e0");
    doc.fontSize(7.5).fillColor("#bbbbbb").font("Helvetica")
      .text(
        `Generated by MIA  ·  mia-dpp.vercel.app  ·  ${new Date().toISOString().slice(0, 10)}  ·  IDTA AAS v3.0  ·  EU ESPR compliant`,
        MARGIN, H - 32,
        { align: "center", width: CW }
      );
  }

  doc.end();
  const pdfBuffer = await pdfPromise;

  const filename = `${String(product_name).replace(/[^a-z0-9]/gi, "_").toLowerCase()}-dpp.pdf`;
  return new Response(new Uint8Array(pdfBuffer), {
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": `attachment; filename="${filename}"`,
      "Cache-Control": "no-store",
    },
  });
}
