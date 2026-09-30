"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

interface PassportRecord {
  id: string;
  thread_id: string;
  product_name: string;
  submodel: string;
  status: string;
  qr_code_b64: string | null;
  passport_url: string | null;
  product_image_url: string | null;
  aas_json: Record<string, unknown> | null;
  created_at: string;
}

interface AasElement {
  idShort: string;
  valueType?: string;
  value?: unknown;
  modelType?: string;
  submodelElements?: AasElement[];
  statements?: AasElement[];
}

interface AasSubmodel {
  idShort?: string;
  id?: string;
  submodelElements?: AasElement[];
}

interface ParsedField {
  label: string;
  value: string;
}

interface ParsedSection {
  key: string;
  label: string;
  idtaCode: string;
  fields: ParsedField[];
}

const SUBMODEL_META: Record<string, { label: string; idtaCode: string; icon: string }> = {
  Nameplate:               { label: "Digital Nameplate",        idtaCode: "IDTA 02006", icon: "🏷" },
  DigitalNameplate:        { label: "Digital Nameplate",        idtaCode: "IDTA 02006", icon: "🏷" },
  digital_nameplate:       { label: "Digital Nameplate",        idtaCode: "IDTA 02006", icon: "🏷" },
  TechnicalData:           { label: "Technical Data",           idtaCode: "IDTA 02003", icon: "⚙️" },
  technical_data:          { label: "Technical Data",           idtaCode: "IDTA 02003", icon: "⚙️" },
  DPPMetadata:             { label: "DPP Metadata",             idtaCode: "IDTA 02099", icon: "📋" },
  dpp_metadata:            { label: "DPP Metadata",             idtaCode: "IDTA 02099", icon: "📋" },
  CarbonFootprint:         { label: "Carbon Footprint",         idtaCode: "IDTA 02023", icon: "🌿" },
  carbon_footprint:        { label: "Carbon Footprint",         idtaCode: "IDTA 02023", icon: "🌿" },
  HandoverDocumentation:   { label: "Handover Documentation",   idtaCode: "IDTA 02004", icon: "📄" },
  handover_documentation:  { label: "Handover Documentation",   idtaCode: "IDTA 02004", icon: "📄" },
  MaintenanceInstructions: { label: "Maintenance Instructions", idtaCode: "IDTA 02018", icon: "🔧" },
  maintenance_instructions:{ label: "Maintenance Instructions", idtaCode: "IDTA 02018", icon: "🔧" },
};

function extractValue(el: AasElement): string | null {
  if (el.modelType === "Property" && el.value != null) {
    return String(el.value);
  }
  if (el.modelType === "MultiLanguageProperty" && Array.isArray(el.value)) {
    const langs = el.value as Array<{ language: string; text: string }>;
    const en = langs.find((l) => l.language === "en") ?? langs[0];
    return en?.text ?? null;
  }
  return null;
}

function collectFields(elements: AasElement[]): ParsedField[] {
  const fields: ParsedField[] = [];
  for (const el of elements) {
    const val = extractValue(el);
    if (val) {
      fields.push({ label: formatLabel(el.idShort), value: val });
    } else if (el.submodelElements?.length) {
      fields.push(...collectFields(el.submodelElements));
    } else if (el.statements?.length) {
      fields.push(...collectFields(el.statements));
    }
  }
  return fields;
}

function formatLabel(idShort: string): string {
  // Insert space before uppercase sequences, handle acronyms
  return idShort
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2")
    .replace(/_/g, " ")
    .replace(/^./, (s) => s.toUpperCase())
    .trim();
}

function parseSections(aasJson: Record<string, unknown>): ParsedSection[] {
  const submodels = (aasJson.submodels as AasSubmodel[] | undefined) ?? [];
  const sections: ParsedSection[] = [];

  for (const sm of submodels) {
    const key = sm.idShort ?? sm.id ?? "unknown";
    const meta = SUBMODEL_META[key] ?? {
      label: formatLabel(key),
      idtaCode: "AAS",
      icon: "📦",
    };
    const fields = collectFields(sm.submodelElements ?? []);
    if (fields.length > 0) {
      sections.push({ key, label: meta.label, idtaCode: meta.idtaCode, fields });
    }
  }
  return sections;
}

// Pull manufacturer name and product designation for header
function getHeaderFields(sections: ParsedSection[]): { manufacturer: string; product: string; uri: string } {
  let manufacturer = "";
  let product = "";
  let uri = "";
  for (const s of sections) {
    for (const f of s.fields) {
      if (!manufacturer && f.label.toLowerCase().includes("manufacturer name")) manufacturer = f.value;
      if (!product && (f.label.toLowerCase().includes("product designation") || f.label.toLowerCase().includes("product name"))) product = f.value;
      if (!uri && (f.label.toLowerCase().includes("uri") || f.label.toLowerCase().includes("product url"))) uri = f.value;
    }
  }
  return { manufacturer, product, uri };
}

export default function PassportPage() {
  const params = useParams();
  const threadId = typeof params.id === "string" ? params.id : Array.isArray(params.id) ? params.id[0] : "";

  const [passport, setPassport] = useState<PassportRecord | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeSection, setActiveSection] = useState(0);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!threadId) return;
    fetch(`/api/passports/thread/${encodeURIComponent(threadId)}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.error) throw new Error(data.error);
        setPassport(data as PassportRecord);
      })
      .catch((e) => setLoadError(e.message))
      .finally(() => setLoading(false));
  }, [threadId]);

  const sections = passport?.aas_json ? parseSections(passport.aas_json) : [];
  const header = getHeaderFields(sections);
  const activeFields = sections[activeSection]?.fields ?? [];

  function copyLink() {
    navigator.clipboard.writeText(window.location.href);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f9f9f9]">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-[#e0e0e0]" style={{ borderTopColor: "#1a1a1a" }} />
          <p className="text-[13px] text-[#999]">Loading passport…</p>
        </div>
      </div>
    );
  }

  if (loadError || !passport) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f9f9f9]">
        <div className="max-w-sm rounded-2xl border border-[#f0d0d0] bg-white p-8 text-center shadow-sm">
          <p className="text-[15px] font-semibold text-[#c0392b]">Passport not found</p>
          <p className="mt-1.5 text-[13px] text-[#999]">{loadError ?? "This passport may have been removed or the link is incorrect."}</p>
        </div>
      </div>
    );
  }

  const isDeployed = passport.status === "deployed";
  const passportUrl = passport.passport_url ?? window.location.href;

  return (
    <div className="min-h-screen bg-[#f5f5f5]" style={{ fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}>

      {/* Top nav */}
      <header className="sticky top-0 z-10 border-b border-[#e8e8e8] bg-white/90 backdrop-blur-sm">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-2.5">
            <div className="grid h-7 w-7 place-items-center rounded-lg bg-[#1a1a1a]">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <span className="text-[14px] font-semibold text-[#1a1a1a]">MIA</span>
            <span className="text-[#d0d0d0]">/</span>
            <span className="text-[13px] text-[#888]">Digital Product Passport</span>
          </div>
          <div className="flex items-center gap-2">
            {passport.aas_json && (
              <a
                href={`/api/passports/thread/${threadId}/download`}
                download
                className="flex items-center gap-1.5 rounded-lg border border-[#e8e8e8] bg-white px-3 py-1.5 text-[12px] font-medium text-[#555] transition-colors hover:bg-[#f5f5f5]"
              >
                <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M8 2v9M8 11l-3-3M8 11l3-3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/><path d="M2 13h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>
                AAS JSON
              </a>
            )}
            <button
              onClick={copyLink}
              className="flex items-center gap-1.5 rounded-lg border border-[#e8e8e8] bg-white px-3 py-1.5 text-[12px] font-medium text-[#555] transition-colors hover:bg-[#f5f5f5]"
            >
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M10 2H4a1 1 0 0 0-1 1v9h1V3h6V2z" fill="currentColor"/><rect x="5" y="4" width="8" height="10" rx="1" stroke="currentColor" strokeWidth="1.3" fill="none"/></svg>
              {copied ? "Copied!" : "Copy link"}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-8">

        {/* Hero card */}
        <div className="mb-6 overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-[#e8e8e8]">
          <div className="flex items-start gap-6 p-6">
            {/* Product image */}
            <div className="flex h-24 w-24 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-[#f0f0f0] bg-[#fafafa]">
              {passport.product_image_url ? (
                <img
                  src={passport.product_image_url}
                  alt={passport.product_name}
                  className="h-full w-full object-contain p-2"
                  onError={(e) => ((e.target as HTMLImageElement).style.display = "none")}
                />
              ) : (
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#d0d0d0" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="3" width="20" height="14" rx="2" />
                  <path d="M8 21h8M12 17v4" />
                </svg>
              )}
            </div>

            {/* Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-[12px] font-medium uppercase tracking-wider text-[#aaa]">
                    {header.manufacturer || "Digital Product Passport"}
                  </p>
                  <h1 className="mt-0.5 text-[22px] font-bold tracking-tight text-[#1a1a1a]">
                    {passport.product_name}
                  </h1>
                  {header.uri && (
                    <a
                      href={header.uri}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-1 inline-block text-[12px] text-[#3b5bdb] hover:underline"
                    >
                      {header.uri.replace(/^https?:\/\//, "").split("/")[0]} →
                    </a>
                  )}
                </div>
                <div className="flex flex-col items-end gap-1.5 shrink-0">
                  <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold ${isDeployed ? "bg-[#e8f5ee] text-[#1b8a5a]" : "bg-[#fff8e6] text-[#b45309]"}`}>
                    <span className={`h-1.5 w-1.5 rounded-full ${isDeployed ? "bg-[#1b8a5a]" : "bg-[#b45309]"}`} />
                    {isDeployed ? "Active" : "Draft"}
                  </span>
                </div>
              </div>

              {/* Standards strip */}
              <div className="mt-4 flex flex-wrap gap-1.5">
                {sections.map((s) => (
                  <span key={s.key} className="rounded-md border border-[#e0e8ff] bg-[#f0f4ff] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#3b5bdb]">
                    {s.idtaCode}
                  </span>
                ))}
                <span className="rounded-md border border-[#e0e8ff] bg-[#f0f4ff] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#3b5bdb]">
                  AAS v3.0
                </span>
                <span className="rounded-md border border-[#e0e8ff] bg-[#f0f4ff] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#3b5bdb]">
                  EU ESPR
                </span>
              </div>
            </div>
          </div>

          {/* QR code row */}
          {passport.qr_code_b64 && (
            <div className="flex items-center gap-6 border-t border-[#f0f0f0] px-6 py-5">
              <img
                src={`data:image/png;base64,${passport.qr_code_b64}`}
                alt="Passport QR Code"
                className="h-24 w-24 rounded-xl"
                style={{ imageRendering: "pixelated" }}
              />
              <div>
                <p className="text-[13px] font-semibold text-[#1a1a1a]">Scan to share this passport</p>
                <p className="mt-0.5 text-[12px] text-[#888]">Publicly accessible · EU ESPR compliant</p>
                <p className="mt-2 break-all font-mono text-[10px] text-[#bbb]">{passportUrl}</p>
              </div>
            </div>
          )}
        </div>

        {/* Section tabs + data */}
        {sections.length > 0 && (
          <div className="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-[#e8e8e8]">
            {/* Tab bar */}
            <div className="flex overflow-x-auto border-b border-[#f0f0f0] px-2 pt-2">
              {sections.map((s, i) => (
                <button
                  key={s.key}
                  onClick={() => setActiveSection(i)}
                  className={[
                    "shrink-0 rounded-t-lg px-4 py-2.5 text-[13px] font-medium transition-colors whitespace-nowrap",
                    activeSection === i
                      ? "border-b-2 border-[#1a1a1a] text-[#1a1a1a]"
                      : "text-[#999] hover:text-[#555]",
                  ].join(" ")}
                >
                  {s.label}
                  <span className="ml-1.5 rounded-full bg-[#f0f0f0] px-1.5 py-0.5 text-[10px] font-semibold text-[#888]">
                    {s.fields.length}
                  </span>
                </button>
              ))}
            </div>

            {/* Active section fields */}
            <div className="p-6">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <p className="text-[15px] font-semibold text-[#1a1a1a]">{sections[activeSection]?.label}</p>
                  <p className="text-[12px] text-[#aaa]">{sections[activeSection]?.idtaCode} · {activeFields.length} fields</p>
                </div>
              </div>

              <div className="divide-y divide-[#f5f5f5]">
                {activeFields.map(({ label, value }, i) => (
                  <div key={i} className="flex items-start gap-4 py-3">
                    <p className="w-52 shrink-0 text-[13px] text-[#888]">{label}</p>
                    <p className="flex-1 text-[13px] font-medium text-[#1a1a1a] break-words">
                      {value.startsWith("http") ? (
                        <a href={value} target="_blank" rel="noopener noreferrer" className="text-[#3b5bdb] hover:underline break-all">
                          {value}
                        </a>
                      ) : value}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* No data state */}
        {sections.length === 0 && (
          <div className="rounded-2xl border border-[#e8e8e8] bg-white p-12 text-center">
            <p className="text-[15px] font-semibold text-[#1a1a1a]">No structured data available</p>
            <p className="mt-1.5 text-[13px] text-[#999]">This passport hasn't been generated yet, or data is still being processed.</p>
          </div>
        )}

        {/* Passport identity */}
        <div className="mt-6 rounded-2xl bg-white p-5 shadow-sm ring-1 ring-[#e8e8e8]">
          <p className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-[#bbb]">Passport Identity</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <p className="text-[11px] text-[#bbb]">Passport ID</p>
              <p className="mt-0.5 break-all font-mono text-[11px] text-[#555]">{threadId}</p>
            </div>
            <div>
              <p className="text-[11px] text-[#bbb]">Issued</p>
              <p className="mt-0.5 text-[12px] text-[#555]">
                {new Date(passport.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}
              </p>
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <path d="M8 1.5l1.854 3.754 4.146.603-3 2.923.708 4.12L8 10.75l-3.708 1.95.708-4.12L2 5.857l4.146-.603L8 1.5z" fill="#1b8a5a" />
            </svg>
            <p className="text-[12px] font-medium text-[#1b8a5a]">IDTA compliant · Machine-readable AAS v3.0</p>
          </div>
        </div>
      </main>

      <footer className="border-t border-[#eee] px-6 py-5 text-center">
        <p className="text-[12px] text-[#bbb]">
          Generated by{" "}
          <a href="https://mia-dpp.vercel.app" className="font-medium text-[#3b5bdb]" target="_blank" rel="noopener noreferrer">
            MIA
          </a>{" "}
          · Mittelstand Integration Agent
        </p>
      </footer>
    </div>
  );
}
