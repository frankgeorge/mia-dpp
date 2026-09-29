"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface Passport {
  id: string;
  thread_id: string;
  product_name: string;
  submodel: string;
  status: "draft" | "deployed";
  passport_url: string | null;
  product_image_url: string | null;
  aas_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

interface AasProperty {
  idShort: string;
  modelType?: string;
  value?: string;
  valueType?: string;
  submodelElements?: AasProperty[];
  statements?: AasProperty[];
}

function collectProperties(elements: AasProperty[]): { path: string; label: string; value: string }[] {
  const results: { path: string; label: string; value: string }[] = [];
  function walk(items: AasProperty[], prefix: string) {
    for (const el of items) {
      const path = prefix ? `${prefix} / ${el.idShort}` : el.idShort;
      if (el.modelType === "Property" && el.value !== undefined) {
        results.push({ path, label: el.idShort, value: String(el.value) });
      }
      if (el.submodelElements) walk(el.submodelElements, path);
      if (el.statements) walk(el.statements, path);
    }
  }
  walk(elements, "");
  return results;
}

function formatLabel(s: string) {
  return s.replace(/([A-Z])/g, " $1").replace(/^./, (c) => c.toUpperCase()).trim();
}

function AasViewer({ aas_json }: { aas_json: Record<string, unknown> }) {
  const submodels = (aas_json.submodels as AasProperty[] | undefined) ?? [];
  const shells = (aas_json.assetAdministrationShells as { idShort?: string; id?: string }[] | undefined) ?? [];
  const shellId = shells[0]?.id ?? "";
  const shellName = shells[0]?.idShort ?? "Asset Administration Shell";

  const [showRaw, setShowRaw] = useState(false);

  return (
    <div className="space-y-4">
      {/* Shell header */}
      <div className="rounded-xl border border-hairline bg-mist p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Asset Administration Shell</p>
            <p className="mt-0.5 text-[14px] font-semibold text-ink">{shellName}</p>
            {shellId && <p className="mt-0.5 break-all font-mono text-[10px] text-muted">{shellId}</p>}
          </div>
          <button
            onClick={() => setShowRaw((v) => !v)}
            className="rounded-lg border border-hairline px-3 py-1.5 text-[11px] font-medium text-muted hover:text-ink"
          >
            {showRaw ? "Structured view" : "Raw JSON"}
          </button>
        </div>
      </div>

      {showRaw ? (
        <pre className="overflow-x-auto rounded-xl border border-hairline bg-mist p-4 font-mono text-[11px] text-ink">
          {JSON.stringify(aas_json, null, 2)}
        </pre>
      ) : (
        submodels.map((sm, i) => {
          const props = collectProperties(sm.submodelElements ?? []);
          return (
            <div key={i} className="rounded-xl border border-hairline bg-paper">
              <div className="border-b border-hairline px-4 py-3">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Submodel</p>
                <p className="mt-0.5 text-[13px] font-semibold text-ink">{sm.idShort}</p>
              </div>
              <div className="divide-y divide-hairline">
                {props.length === 0 ? (
                  <p className="px-4 py-3 text-[12px] text-muted">No properties found.</p>
                ) : (
                  props.map(({ path, label, value }) => (
                    <div key={path} className="flex items-start justify-between gap-4 px-4 py-2.5">
                      <span className="text-[12px] text-muted">{formatLabel(label)}</span>
                      <span className="text-right text-[12px] font-medium text-ink">{value}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}

export default function AasPage() {
  const [passports, setPassports] = useState<Passport[]>([]);
  const [selected, setSelected] = useState<Passport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/passports")
      .then((r) => r.json())
      .then((data) => {
        const list = (Array.isArray(data) ? data : []) as Passport[];
        const deployed = list.filter((p) => p.status === "deployed" && p.aas_json);
        setPassports(deployed);
        if (deployed.length > 0) setSelected(deployed[0]);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="px-8 py-8">
      <div className="mx-auto max-w-shell">
        <div className="mb-8">
          <h1 className="text-[22px] font-semibold tracking-tight text-ink">Asset Administration Shell</h1>
          <p className="mt-1 text-[13px] text-muted">Inspect the AAS data for your deployed Digital Product Passports.</p>
        </div>

        {loading ? (
          <div className="flex min-h-[300px] items-center justify-center">
            <div className="flex gap-1.5">
              {[0, 1, 2].map((i) => (
                <span key={i} className="h-2 w-2 animate-pulse rounded-full bg-muted" style={{ animationDelay: `${i * 150}ms` }} />
              ))}
            </div>
          </div>
        ) : passports.length === 0 ? (
          <div className="flex min-h-[300px] items-center justify-center rounded-2xl border border-hairline bg-paper">
            <div className="max-w-xs px-8 py-12 text-center">
              <p className="text-[15px] font-semibold text-ink">No deployed passports yet</p>
              <p className="mt-2 text-[13px] text-muted">Generate and deploy a Digital Product Passport to see its AAS data here.</p>
              <Link
                href="/workspace"
                className="mt-5 inline-flex items-center gap-2 rounded-full bg-ink px-5 py-2.5 text-[13px] font-medium text-white transition-all hover:-translate-y-px hover:shadow-md"
              >
                New passport
              </Link>
            </div>
          </div>
        ) : (
          <div className="flex gap-6">
            {/* Passport list */}
            <div className="w-56 shrink-0 space-y-1">
              {passports.map((p) => (
                <button
                  key={p.id}
                  onClick={() => setSelected(p)}
                  className={`w-full rounded-xl border px-3 py-2.5 text-left transition-colors ${
                    selected?.id === p.id
                      ? "border-signal/30 bg-signal/5 text-ink"
                      : "border-hairline bg-paper text-muted hover:text-ink"
                  }`}
                >
                  {p.product_image_url && (
                    <img src={p.product_image_url} alt={p.product_name} className="mb-2 h-10 w-full rounded-md object-contain" />
                  )}
                  <p className="truncate text-[13px] font-medium">{p.product_name}</p>
                  <p className="mt-0.5 font-mono text-[10px] text-muted">{p.submodel}</p>
                  <p className="mt-1 text-[10px] text-muted">
                    {new Date(p.updated_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
                  </p>
                </button>
              ))}
            </div>

            {/* AAS viewer */}
            <div className="min-w-0 flex-1">
              {selected?.aas_json ? (
                <AasViewer aas_json={selected.aas_json} />
              ) : (
                <p className="text-[13px] text-muted">Select a passport to view its AAS.</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
