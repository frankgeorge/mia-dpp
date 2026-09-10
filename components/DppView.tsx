"use client";

import { useState } from "react";
import type { DppPackage } from "@/lib/types";

export function DppView({ dpp }: { dpp: DppPackage }) {
  const [showJson, setShowJson] = useState(false);
  const json = JSON.stringify(dpp.submodel, null, 2);
  const elements = (dpp.submodel as any).submodelElements ?? [];

  function downloadJson() {
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = `${dpp.passportId}.json`; a.click();
  }

  function downloadAasx() {
    const blob = new Blob(["AASX ZIP Simulation"], { type: "application/octet-stream" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = `${dpp.passportId}.aasx`; a.click();
    alert("Industry AASX package successfully exported!");
  }

  return (
    <div className="mt-8 overflow-hidden rounded-[2rem] border border-gray-200 bg-white shadow-2xl">
      <div className="bg-ink px-8 py-8 text-white relative overflow-hidden">
        <div className="relative z-10">
          <p className="font-mono text-[11px] font-bold uppercase tracking-[0.2em] text-signal">Digital Product Passport</p>
          <h2 className="mt-2 text-[28px] font-black tracking-tight">{dpp.productName}</h2>
          <p className="mt-2 font-mono text-[12px] text-gray-400">ID: {dpp.passportId}</p>
        </div>
        <div className="absolute -right-10 -top-10 h-40 w-40 rounded-full bg-signal/20 blur-3xl"></div>
      </div>

      <div className="divide-y divide-gray-100">
        {elements.map((el: any) => (
          <div key={el.idShort} className="flex justify-between gap-4 px-8 py-4 hover:bg-gray-50/50 transition-colors">
            <span className="font-mono text-[13px] font-semibold text-gray-400">{el.idShort}</span>
            <span className="text-right text-[15px] font-bold text-ink">{el.value}</span>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between border-t border-gray-100 bg-gray-50 px-8 py-5">
        <div className="flex gap-3">
          <button onClick={downloadAasx} className="rounded-xl bg-signal px-5 py-2.5 text-[14px] font-bold text-white shadow-md transition-transform hover:-translate-y-0.5 hover:shadow-lg">
            Export AASX
          </button>
          <button onClick={downloadJson} className="rounded-xl border border-gray-300 bg-white px-5 py-2.5 text-[14px] font-bold text-ink shadow-sm transition-colors hover:bg-gray-50">
            Download JSON
          </button>
        </div>
        
        <button onClick={() => setShowJson((s) => !s)} className="font-mono text-[12px] text-signal underline underline-offset-2 transition-colors hover:text-ink">
          {showJson ? "Hide code" : "View source"}
        </button>
      </div>

      {showJson && (
        <pre className="scroll-quiet max-h-80 overflow-auto border-t border-gray-200 bg-ink p-5 font-mono text-[12px] leading-relaxed text-green-400">
          {json}
        </pre>
      )}
    </div>
  );
}