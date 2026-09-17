"use client";

import { useEffect, useState } from "react";

const ROWS = [
  { raw: "AFRISO-EURO-INDEX GmbH", field: "NAME1", target: "ManufacturerName", c: 0.97 },
  { raw: "RF100-16", field: "MATNR_TXT", target: "ProductDesignation", c: 0.93 },
  { raw: "SN 2024-8871", field: "SERNR", target: "SerialNumber", c: 0.96 },
  { raw: "Güglingen, DE", field: "WERKS", target: "ManufacturingSite", c: 0.86 },
  { raw: "IP65", field: "SCHUTZART", target: "DegreeOfProtection", c: 0.94 },
  { raw: "0–16 bar", field: "MESSBEREICH", target: "MeasuringRange", c: 0.88 },
];

export function Nameplate() {
  const [mapped, setMapped] = useState(false);

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      const immediate = setTimeout(() => setMapped(true), 0);
      return () => clearTimeout(immediate);
    }
    const t = setTimeout(() => setMapped(true), 1400);
    const loop = setInterval(() => setMapped((m) => !m), 6000);
    return () => {
      clearTimeout(t);
      clearInterval(loop);
    };
  }, []);

  return (
    <div className="relative">
      {/* The plate */}
      <div
        className="relative overflow-hidden rounded-xl border border-hairline"
        style={{
          background:
            "linear-gradient(160deg,#FAFAFB 0%,#F0F0F2 38%,#F7F7F8 60%,#EDEDEF 100%)",
          boxShadow:
            "0 1px 0 rgba(255,255,255,.9) inset, 0 18px 40px -22px rgba(0,0,0,.35)",
        }}
      >
        {/* rivets */}
        {[
          "left-3 top-3",
          "right-3 top-3",
          "left-3 bottom-3",
          "right-3 bottom-3",
        ].map((p) => (
          <span
            key={p}
            className={`absolute ${p} h-2 w-2 rounded-full border border-black/10 bg-white/70`}
            style={{ boxShadow: "0 1px 2px rgba(0,0,0,.18) inset" }}
          />
        ))}

        <div className="px-8 py-7">
          <div className="flex items-baseline justify-between border-b border-black/10 pb-3">
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-ink/60">
              Typenschild
            </p>
            <p className="font-mono text-[10px] text-ink/40">
              {mapped ? "MAPPED" : "SOURCE"}
            </p>
          </div>

          <div className="mt-4 space-y-2.5">
            {ROWS.map((r, i) => (
              <div
                key={r.field}
                className="grid grid-cols-[1fr_auto] items-center gap-3"
                style={{
                  animation: `etch .5s cubic-bezier(.16,1,.3,1) both`,
                  animationDelay: `${i * 70}ms`,
                }}
              >
                <div className="min-w-0">
                  {mapped ? (
                    <p className="truncate font-mono text-[12px] leading-5 text-ink">
                      <span className="text-signal">{r.target}</span>
                      <span className="text-ink/35"> = </span>
                      {r.raw}
                    </p>
                  ) : (
                    <p className="truncate font-mono text-[12px] leading-5 text-ink/70">
                      <span className="text-ink/35">{r.field}</span>{" "}
                      {r.raw}
                    </p>
                  )}
                </div>
                <span
                  className="font-mono text-[10px] tabular-nums transition-opacity duration-500"
                  style={{
                    opacity: mapped ? 1 : 0,
                    color: r.c >= 0.85 ? "#1B8A5A" : "#B8760B",
                  }}
                >
                  {r.c.toFixed(2)}
                </span>
              </div>
            ))}
          </div>

          <div className="mt-5 flex items-center justify-between border-t border-black/10 pt-3">
            <p className="font-mono text-[10px] text-ink/40">
              IDTA 02006 · Digital Nameplate
            </p>
            <span
              className="rounded-full px-2 py-0.5 font-mono text-[10px] transition-colors duration-500"
              style={{
                background: mapped ? "#E7F0FC" : "transparent",
                color: mapped ? "#0B5FD0" : "#6E6E73",
              }}
            >
              {mapped ? "6 elements" : "6 lines"}
            </span>
          </div>
        </div>
      </div>

      <p className="mt-4 text-center font-mono text-[11px] text-muted">
        The same plate, before and after mapping.
      </p>
    </div>
  );
}
