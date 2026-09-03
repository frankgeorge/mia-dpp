"use client";

import { useState } from "react";
import type { DppPackage } from "@/lib/types";

export function DppView({ dpp }: { dpp: DppPackage }) {
  const [showJson, setShowJson] = useState(false);
  const json = JSON.stringify(dpp.submodel, null, 2);
  const elements = (dpp.submodel as any).submodelElements ?? [];

  function download() {
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${dpp.passportId.replace(/[:]/g, "_")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="mt-5 overflow-hidden rounded-2xl border border-hairline bg-paper">
      <div className="border-b border-hairline bg-ink px-5 py-4 text-white">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-white/50">
          Digital Product Passport
        </p>
        <p className="mt-1.5 text-[17px] font-semibold tracking-tight">
          {dpp.productName}
        </p>
        <p className="mt-1 break-all font-mono text-[11px] text-white/45">
          {dpp.passportId}
        </p>
      </div>

      <div className="divide-y divide-hairline">
        {elements.map((el: any) => (
          <div
            key={el.idShort}
            className="flex items-baseline justify-between gap-4 px-5 py-2.5"
          >
            <span className="font-mono text-[12px] text-muted">
              {el.idShort}
            </span>
            <span className="truncate text-right text-[13px]">{el.value}</span>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-hairline p-4">
        <button
          onClick={download}
          className="rounded-full bg-signal px-4 py-2 text-[13px] font-medium text-white transition-opacity hover:opacity-88"
        >
          Download package
        </button>
        <button
          onClick={() => setShowJson((s) => !s)}
          className="rounded-full border border-hairline px-4 py-2 text-[13px] font-medium transition-colors hover:bg-mist"
        >
          {showJson ? "Hide" : "View"} submodel
        </button>
        <span className="ml-auto font-mono text-[11px] text-muted">
          {elements.length} elements
        </span>
      </div>

      {showJson && (
        <pre className="scroll-quiet max-h-72 overflow-auto border-t border-hairline bg-mist p-4 font-mono text-[11px] leading-relaxed">
          {json}
        </pre>
      )}
    </div>
  );
}
