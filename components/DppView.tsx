"use client";

import { useEffect, useState } from "react";
import type { DppPackage } from "@/lib/standards/types";

export function DppView({ dpp }: { dpp: DppPackage }) {
  const [showJson, setShowJson] = useState(false);
  const [passportUrl, setPassportUrl] = useState("");
  const [copied, setCopied] = useState(false);

  const json = JSON.stringify(dpp.submodel, null, 2);
  const elements = (dpp.submodel as any).submodelElements ?? [];

  // Save passport to server and get a shareable URL
  useEffect(() => {
    fetch("/api/passport", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dpp }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.url) setPassportUrl(data.url);
      })
      .catch(() => { /* non-critical */ });
  }, [dpp.passportId]);

  function download() {
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${dpp.passportId.replace(/[:]/g, "_")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function copyLink() {
    if (!passportUrl) return;
    navigator.clipboard.writeText(passportUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="mt-5 overflow-hidden rounded-2xl border border-hairline bg-paper">
      {/* Header */}
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

      {/* Fields */}
      <div className="divide-y divide-hairline">
        {elements.map((el: any) => (
          <div
            key={el.idShort}
            className="flex items-baseline justify-between gap-4 px-5 py-2.5"
          >
            <span className="font-mono text-[12px] text-muted">{el.idShort}</span>
            <span className="truncate text-right text-[13px]">{el.value}</span>
          </div>
        ))}
      </div>

      {/* Hosted link */}
      {passportUrl && (
        <div className="flex items-center gap-2 border-t border-hairline bg-mist px-5 py-3">
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" className="shrink-0 text-muted">
            <path d="M6.5 9.5a4 4 0 005.657-5.657L10.5 2.2A4 4 0 004.843 7.857M9.5 6.5a4 4 0 00-5.657 5.657l1.657 1.657A4 4 0 0011.157 8.15" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
          </svg>
          <p className="flex-1 truncate font-mono text-[11px] text-muted">{passportUrl}</p>
          <button
            onClick={copyLink}
            className="shrink-0 rounded-lg border border-hairline bg-paper px-2.5 py-1 text-[11px] font-medium transition-colors hover:bg-mist"
          >
            {copied ? "Copied!" : "Copy link"}
          </button>
          <a
            href={passportUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 rounded-lg border border-hairline bg-paper px-2.5 py-1 text-[11px] font-medium text-signal transition-colors hover:bg-mist"
          >
            Open ↗
          </a>
        </div>
      )}

      {/* Actions */}
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
