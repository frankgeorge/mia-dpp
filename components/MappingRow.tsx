"use client";

import { useState } from "react";
import type { FieldMapping, NameplateElement } from "@/lib/types";

export function MappingRow({
  mapping: m,
  elements,
  onDecide,
  onCorrect,
}: {
  mapping: FieldMapping;
  elements: NameplateElement[];
  onDecide: (id: string, status: "approved" | "rejected") => void;
  onCorrect: (id: string, target: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const pct = Math.round(m.confidence * 100);
  const strong = m.confidence >= 0.85;

  // FEATURE 1 LOGIK: Herausfinden ob das Feld Pflicht ist
  const targetDef = elements.find((e) => e.name === m.targetElement);
  const isRequired = targetDef?.required;

  const tone =
    m.status === "rejected"
      ? "opacity-45 grayscale"
      : m.status === "review"
      ? "border-orange-200 shadow-md ring-1 ring-orange-500/10"
      : "border-gray-100 shadow-sm hover:shadow-md";

  return (
    <div className={`rounded-2xl border bg-white p-5 transition-all duration-300 hover:-translate-y-1 ${tone}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 font-mono text-[13px] font-semibold text-gray-600">
            <span className="bg-gray-100 px-2 py-1 rounded border border-gray-200">{m.sourceField}</span>
            <span className="text-gray-300">&rarr;</span>
            <span className="text-signal">
              {m.targetElement}
              {/* FEATURE 1 UI: Rotes Sternchen für Pflichtfeld */}
              {isRequired && <span className="text-red-500 ml-1" title="Required by EU Norm">*</span>}
            </span>
          </p>
          <p className="mt-3 truncate text-[18px] font-bold text-ink">{m.sourceValue}</p>
          
          {/* FEATURE 1 UI: Semantic ID in kleiner, grauer Schrift */}
          <p className="mt-1 font-mono text-[10px] text-gray-400 font-medium">
            Semantic ID: {m.semanticId}
          </p>
        </div>
        
        <div className="flex flex-col items-end">
          <span className="font-mono text-[22px] font-black tabular-nums tracking-tighter" style={{ color: strong ? "#10B981" : "#F97316" }}>
            {pct}%
          </span>
          <span className="text-[9px] font-bold uppercase tracking-wider text-gray-400">Confidence</span>
        </div>
      </div>

      <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
        <div
          className="h-full rounded-full transition-all duration-1000"
          style={{ width: `${pct}%`, background: strong ? "#10B981" : "#F97316" }}
        />
      </div>

      <div className="mt-4 rounded-xl bg-gray-50 p-3 border border-gray-100 text-[13px] leading-relaxed text-gray-600">
        <span className="font-semibold text-gray-400 mr-2">Reasoning:</span>
        {m.reasoning}
      </div>

      {m.fromGraph && (
        <div className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-blue-50 border border-blue-100 px-2.5 py-1 font-mono text-[10px] font-semibold text-signal">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 2v6h-6"></path><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path><path d="M3 2v6h6"></path></svg>
          From Integration Graph
        </div>
      )}

      {/* Approval gate */}
      {m.status === "review" && !editing && (
        <div className="mt-5 flex items-center gap-3 pt-4 border-t border-gray-100">
          <button
            onClick={() => onDecide(m.id, "approved")}
            className="flex-1 rounded-xl bg-ink px-4 py-2.5 text-[13px] font-bold text-white shadow-md transition-transform hover:scale-[1.02]"
          >
            ✓ Approve
          </button>
          <button
            onClick={() => setEditing(true)}
            className="flex-1 rounded-xl border border-gray-200 bg-white px-4 py-2.5 text-[13px] font-semibold text-ink shadow-sm transition-colors hover:bg-gray-50"
          >
            ✎ Change target
          </button>
          <button
            onClick={() => onDecide(m.id, "rejected")}
            className="px-3 text-[13px] font-medium text-gray-400 hover:text-red-500"
          >
            Discard
          </button>
        </div>
      )}

      {editing && (
        <div className="mt-5 rounded-xl bg-blue-50 border border-blue-100 p-4">
          <label className="text-[13px] font-semibold text-signal">
            Map this field to:
            <select
              autoFocus
              defaultValue={m.targetElement}
              onChange={(e) => {
                onCorrect(m.id, e.target.value);
                setEditing(false);
              }}
              className="mt-2 w-full rounded-lg border border-blue-200 bg-white px-3 py-2.5 font-mono text-[13px] text-ink shadow-sm focus:border-signal focus:outline-none"
            >
              {elements.map((e) => (
                <option key={e.name} value={e.name}>
                  {e.name} {e.required ? "(required)" : ""}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {(m.status === "approved" || m.status === "auto") && (
        <p className="mt-5 font-mono text-[11px] font-bold text-green-600 flex items-center gap-1.5 uppercase tracking-wide">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
          {m.status === "auto" ? "Cleared automatically" : "Approved by you"}
        </p>
      )}
      {m.status === "rejected" && (
        <button
          onClick={() => onDecide(m.id, "approved")}
          className="mt-5 font-mono text-[11px] font-semibold text-gray-400 underline underline-offset-2 hover:text-ink"
        >
          Discarded · undo
        </button>
      )}
    </div>
  );
}