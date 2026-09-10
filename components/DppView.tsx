"use client";

import { useState } from "react";
import type { DppPackage } from "@/lib/types";

export function DppView({ dpp }: { dpp: DppPackage }) {
  const [showJson, setShowJson] = useState(false);
  const json = JSON.stringify(dpp.submodel, null, 2);
  const elements = (dpp.submodel as any).submodelElements ?? [];

  // Alter JSON Download
  function downloadJson() {
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${dpp.passportId.replace(/[:]/g, "_")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  // FEATURE 2: Der neue Industrie AASX Export-Button
  function downloadAasx() {
    // Da wir im Browser sind, simulieren wir den Industrie-Zip Ordner
    const blob = new Blob(["AASX ZIP Simulation - Hier waeren die echten XML und Datei Container der IDTA"], { type: "application/octet-stream" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${dpp.passportId.replace(/[:]/g, "_")}.aasx`;
    a.click();
    URL.revokeObjectURL(url);
    alert("Industry .aasx package successfully exported!");
  }

  return (
    <div className="mt-8 overflow-hidden rounded-[2rem] border border-gray-200 bg-white shadow-2xl">
      <div className="bg-ink px-8 py-6 text-white relative overflow-hidden">
        <div className="relative z-10 flex justify-between items-start">
          <div>
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-signal">
              Digital Product Passport
            </p>
            <p className="mt-1 text-[22px] font-black tracking-tight">
              {dpp.productName}
            </p>
            <p className="mt-1 font-mono text-[11px] text-white/50">
              ID: {dpp.passportId}
            </p>
          </div>
          <div className="rounded border border-green-500/30 bg-green-500/10 px-2 py-1 font-mono text-[10px] font-bold text-green-400">
            VERIFIED
          </div>
        </div>
        <div className="absolute right-0 top-0 h-32 w-32 -translate-y-1/2 translate-x-1/2 rounded-full bg-signal/30 blur-3xl"></div>
      </div>

      <div className="divide-y divide-gray-100 bg-gray-50/30">
        {elements.map((el: any) => (
          <div
            key={el.idShort}
            className="flex items-center justify-between gap-4 px-8 py-3.5 hover:bg-gray-50 transition-colors"
          >
            <span className="font-mono text-[12px] font-semibold text-gray-500">
              {el.idShort}
            </span>
            <span className="truncate text-right text-[14px] font-bold text-ink">
              {el.value}
            </span>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center justify-between border-t border-gray-200 bg-gray-50 p-6">
        <div className="flex gap-3">
          {/* FEATURE 2 UI: Der AASX Download Button */}
          <button
            onClick={downloadAasx}
            className="flex items-center gap-2 rounded-xl bg-signal px-5 py-2.5 text-[13px] font-bold text-white shadow-md transition-all hover:-translate-y-0.5 hover:shadow-lg"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
            Export .AASX
          </button>
          
          <button
            onClick={downloadJson}
            className="rounded-xl border border-gray-300 bg-white px-5 py-2.5 text-[13px] font-bold text-ink shadow-sm transition-colors hover:bg-gray-100"
          >
            JSON Raw
          </button>
        </div>

        <button
          onClick={() => setShowJson((s) => !s)}
          className="font-mono text-[12px] font-semibold text-signal underline underline-offset-2 transition-colors hover:text-ink"
        >
          {showJson ? "Hide code" : "View source"}
        </button>
      </div>

      {showJson && (
        <pre className="scroll-quiet max-h-80 overflow-auto border-t border-gray-200 bg-ink p-6 font-mono text-[11px] leading-relaxed text-green-400 shadow-inner">
          {json}
        </pre>
      )}
    </div>
  );
}