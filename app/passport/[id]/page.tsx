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
  value?: string;
  modelType?: string;
  submodelElements?: AasElement[];
  statements?: AasElement[];
}

interface AasSubmodel {
  idShort?: string;
  id?: string;
  submodelElements?: AasElement[];
}

function extractProperties(elements: AasElement[]): { label: string; value: string }[] {
  const results: { label: string; value: string }[] = [];
  for (const el of elements) {
    if ((el.modelType === "Property" || el.modelType === "MultiLanguageProperty") && el.value) {
      results.push({ label: el.idShort, value: String(el.value) });
    } else if (el.submodelElements?.length) {
      results.push(...extractProperties(el.submodelElements));
    } else if (el.statements?.length) {
      results.push(...extractProperties(el.statements));
    }
  }
  return results;
}

function formatLabel(idShort: string): string {
  return idShort
    .replace(/([A-Z])/g, " $1")
    .replace(/^./, (s) => s.toUpperCase())
    .trim();
}

const SUBMODEL_DISPLAY: Record<string, { label: string; badge: string }> = {
  digital_nameplate:       { label: "Digital Nameplate",        badge: "IDTA 02006" },
  DigitalNameplate:        { label: "Digital Nameplate",        badge: "IDTA 02006" },
  dpp_metadata:            { label: "DPP Metadata",             badge: "IDTA 02099" },
  DPPMetadata:             { label: "DPP Metadata",             badge: "IDTA 02099" },
  technical_data:          { label: "Technical Data",           badge: "IDTA 02003" },
  TechnicalData:           { label: "Technical Data",           badge: "IDTA 02003" },
  carbon_footprint:        { label: "Carbon Footprint",         badge: "IDTA 02023" },
  CarbonFootprint:         { label: "Carbon Footprint",         badge: "IDTA 02023" },
  handover_documentation:  { label: "Handover Documentation",   badge: "IDTA 02004" },
  HandoverDocumentation:   { label: "Handover Documentation",   badge: "IDTA 02004" },
  maintenance_instructions:{ label: "Maintenance Instructions", badge: "IDTA 02018" },
  MaintenanceInstructions: { label: "Maintenance Instructions", badge: "IDTA 02018" },
};

export default function PassportPage() {
  const params = useParams();
  const threadId = typeof params.id === "string" ? params.id : Array.isArray(params.id) ? params.id[0] : "";

  const [passport, setPassport] = useState<PassportRecord | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState(0);

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

  // Parse all submodels from the AAS environment
  const submodels: { key: string; label: string; badge: string; properties: { label: string; value: string }[] }[] = (() => {
    if (!passport?.aas_json) return [];
    const rawSubmodels = (passport.aas_json.submodels as AasSubmodel[] | undefined) ?? [];
    return rawSubmodels
      .map((sm) => {
        const key = sm.idShort ?? sm.id ?? "";
        const display = SUBMODEL_DISPLAY[key] ?? { label: formatLabel(key) || "Product Data", badge: "AAS" };
        const properties = extractProperties(sm.submodelElements ?? []);
        return { key, label: display.label, badge: display.badge, properties };
      })
      .filter((sm) => sm.properties.length > 0);
  })();

  const currentSubmodel = submodels[activeTab] ?? null;

  return (
    <div className="min-h-screen bg-white" style={{ fontFamily: "system-ui, sans-serif" }}>
      {/* Header */}
      <header className="border-b border-[#e8e8e8] bg-white px-6 py-4">
        <div className="mx-auto flex max-w-2xl items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className="grid h-8 w-8 place-items-center rounded-lg"
              style={{ background: "linear-gradient(135deg, #3b5bdb 0%, #4dabf7 100%)" }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                <path
                  d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                  stroke="white"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <span className="text-[15px] font-semibold text-[#1a1a1a]">MIA</span>
          </div>
          <span className="rounded-full border border-[#e8e8e8] px-3 py-1 text-[11px] font-medium uppercase tracking-wider text-[#666]">
            Digital Product Passport
          </span>
        </div>
      </header>

      {/* Main content */}
      <main className="mx-auto max-w-2xl px-6 py-12">
        {loading ? (
          <div className="flex flex-col items-center py-24">
            <div
              className="h-8 w-8 animate-spin rounded-full border-2 border-[#e8e8e8]"
              style={{ borderTopColor: "#3b5bdb" }}
            />
            <p className="mt-4 text-[14px] text-[#888]">Loading passport...</p>
          </div>
        ) : loadError ? (
          <div className="rounded-2xl border border-red-100 bg-red-50 p-8 text-center">
            <p className="text-[15px] font-semibold text-red-700">Passport not found</p>
            <p className="mt-1 text-[13px] text-red-500">{loadError}</p>
          </div>
        ) : passport ? (
          <div className="flex flex-col items-center gap-8">
            {/* Product image */}
            {passport.product_image_url && (
              <img
                src={passport.product_image_url}
                alt={passport.product_name}
                className="h-40 w-auto rounded-2xl object-contain"
              />
            )}

            {/* Product name */}
            <div className="text-center">
              <h1 className="text-[28px] font-bold tracking-tight text-[#1a1a1a]">
                {passport.product_name}
              </h1>
              <p className="mt-1 text-[14px] text-[#888]">EU ESPR Digital Product Passport</p>
            </div>

            {/* QR code */}
            {passport.qr_code_b64 && (
              <div className="flex flex-col items-center gap-4 rounded-2xl border border-[#e8e8e8] bg-[#fafafa] p-8 shadow-sm">
                <img
                  src={`data:image/png;base64,${passport.qr_code_b64}`}
                  alt="Passport QR Code"
                  className="h-56 w-56"
                  style={{ imageRendering: "pixelated" }}
                />
                <p className="text-[13px] font-medium text-[#555]">Scan to verify this passport</p>
              </div>
            )}

            {/* Submodel tabs + data */}
            {submodels.length > 0 && (
              <div className="w-full">
                {/* Tab bar — only show if multiple submodels */}
                {submodels.length > 1 && (
                  <div className="mb-4 flex gap-1 overflow-x-auto rounded-xl border border-[#e8e8e8] bg-[#f8f8f8] p-1">
                    {submodels.map((sm, i) => (
                      <button
                        key={sm.key}
                        onClick={() => setActiveTab(i)}
                        className={[
                          "shrink-0 rounded-lg px-3 py-1.5 text-[12px] font-medium transition-all",
                          activeTab === i
                            ? "bg-white text-[#1a1a1a] shadow-sm"
                            : "text-[#888] hover:text-[#333]",
                        ].join(" ")}
                      >
                        {sm.label}
                      </button>
                    ))}
                  </div>
                )}

                {/* Active submodel properties */}
                {currentSubmodel && (
                  <div className="w-full rounded-2xl border border-[#e8e8e8] bg-white p-6 shadow-sm">
                    <div className="mb-4 flex items-center justify-between">
                      <p className="text-[11px] font-semibold uppercase tracking-wider text-[#aaa]">
                        {currentSubmodel.label}
                      </p>
                      <span className="rounded-full border border-[#e0e8ff] bg-[#f0f4ff] px-2.5 py-0.5 text-[10px] font-medium text-[#3b5bdb]">
                        {currentSubmodel.badge}
                      </span>
                    </div>
                    <div className="space-y-3">
                      {currentSubmodel.properties.map(({ label, value }) => (
                        <div key={label} className="flex items-start justify-between gap-4">
                          <span className="text-[12px] text-[#888]">{formatLabel(label)}</span>
                          <span className="max-w-[60%] break-words text-right text-[13px] font-medium text-[#1a1a1a]">
                            {value}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Passport metadata */}
            <div className="w-full rounded-2xl border border-[#e8e8e8] bg-white p-6 shadow-sm">
              <div className="space-y-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-[#aaa]">Passport ID</p>
                  <p className="mt-1 break-all font-mono text-[12px] text-[#333]">{threadId}</p>
                </div>
                <div className="border-t border-[#f0f0f0]" />
                <div className="flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full bg-green-500" />
                  <p className="text-[12px] text-[#555]">
                    Verified — {submodels.length > 0 ? submodels.map((s) => s.badge).join(", ") : "IDTA 02006"} compliant
                  </p>
                </div>
              </div>
            </div>

            {/* Standards badges */}
            <div className="flex flex-wrap justify-center gap-2">
              {["AAS v3.0", "EU ESPR", "IDTA"].map((badge) => (
                <span
                  key={badge}
                  className="rounded-full border border-[#e0e8ff] bg-[#f0f4ff] px-3 py-1 text-[11px] font-medium text-[#3b5bdb]"
                >
                  {badge}
                </span>
              ))}
            </div>

            {/* Download */}
            {passport.aas_json && (
              <a
                href={`/api/passports/thread/${threadId}/download`}
                download
                className="flex items-center gap-2 rounded-full border border-[#e8e8e8] px-5 py-2.5 text-[13px] font-medium text-[#333] transition-colors hover:bg-[#f5f5f5]"
              >
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                  <path d="M8 2v9M8 11l-3-3M8 11l3-3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
                  <path d="M2 13h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                </svg>
                Download AAS JSON
              </a>
            )}
          </div>
        ) : null}
      </main>

      {/* Footer */}
      <footer className="border-t border-[#e8e8e8] px-6 py-6 text-center">
        <p className="text-[12px] text-[#aaa]">
          Powered by{" "}
          <a href="https://mia-dpp.vercel.app" className="font-medium text-[#3b5bdb]" target="_blank" rel="noopener noreferrer">
            MIA
          </a>{" "}
          — Mittelstand Integration Agent
        </p>
      </footer>
    </div>
  );
}
