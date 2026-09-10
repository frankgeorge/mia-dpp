"use client";

import { useState } from "react";
import type { FieldMapping, NameplateElement } from "@/lib/types";

export function MappingRow({ mapping: m, elements, onDecide, onCorrect }: { mapping: FieldMapping; elements: NameplateElement[]; onDecide: (id: string, status: "approved" | "rejected") => void; onCorrect: (id: string, target: string) => void; }) {
  const [editing, setEditing] = useState(false);
  const pct = Math.round(m.confidence * 100);
  const strong = m.confidence >= 0.85;

  const targetDef = elements.find((e) => e.name === m.targetElement);
  const isRequired = targetDef?.required;

  const border = m.status === "rejected" ? "border-l-gray-300 opacity-50" : m.status === "review" ? "border-l-orange-500 shadow-md ring-1 ring-orange-500/20" : "border-l-green-500 shadow-sm opacity-80";

  return (
    <div className={`relative rounded-2xl border border-gray-100 border-l-4 bg-white p-5 transition-all duration-300 hover:shadow-lg hover:-translate-y-1 ${border}`}>
      <div className="flex justify-between items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3">
            <span className="rounded-lg bg-gray-100 px-2.5 py-1 font-mono text-[11px] font-semibold text-gray-600 border border-gray-200">{m.sourceField}</span>
            <span className="text-gray-300">→</span>
            <span className="font-semibold text-[14px] text-ink">
              {m.targetElement}
              {isRequired && <span className="text-red-500 ml-1.5" title="Required field">*</span>}
            </span>
          </div>
          <p className="mt-3 truncate text-[18px] font-bold text-signal">{m.sourceValue}</p>
          <p className="mt-1.5 font-mono text-[10px] text-gray-400">ID: {m.semanticId}</p>
        </div>
        <div className="flex flex-col items-end">
          <span className="font-mono text-[20px] font-black tabular-nums tracking-tighter" style={{ color: strong ? "#10B981" : "#F97316" }}>{pct}%</span>
          <span className="text-[9px] font-bold uppercase tracking-wider text-gray-400">Confidence</span>
        </div>
      </div>

      {m.sourceQuote && (
        <div className="mt-4 flex items-start gap-2 rounded-lg border border-yellow-200/60 bg-yellow-50/50 p-3 shadow-sm">
          <span className="text-[14px] mt-0.5">🔍</span>
          <div>
            <span className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-yellow-800/60">Source Evidence:</span>
            <span className="rounded bg-yellow-200/50 px-1.5 py-0.5 font-mono text-[12px] italic text-yellow-900">
              {m.sourceQuote}
            </span>
          </div>
        </div>
      )}

      <div className="mt-3 text-[12px] text-gray-600 bg-gray-50 border border-gray-100 p-3 rounded-xl leading-relaxed">
        <span className="font-semibold text-gray-500 mr-2">Reasoning:</span>{m.reasoning}
      </div>

      {m.status === "review" && !editing && (
        <div className="mt-4 flex items-center gap-3 pt-4 border-t border-gray-100">
          <button onClick={() => onDecide(m.id, "approved")} className="flex-1 rounded-xl bg-ink px-4 py-2.5 text-[12px] font-bold text-white shadow-md transition-transform hover:scale-[1.02]">
            ✓ Approve
          </button>
          <button onClick={() => setEditing(true)} className="flex-1 rounded-xl border border-gray-200 bg-white px-4 py-2.5 text-[12px] font-semibold text-ink shadow-sm hover:bg-gray-50">
            ✎ Change target
          </button>
          <button onClick={() => onDecide(m.id, "rejected")} className="px-3 text-[12px] text-gray-400 hover:text-red-500 font-medium">
            Discard
          </button>
        </div>
      )}

      {editing && (
        <div className="mt-4 rounded-xl bg-blue-50 p-4 border border-blue-100">
          <label className="text-[12px] font-semibold text-signal">Map this field to:
            <select autoFocus defaultValue={m.targetElement} onChange={(e) => { onCorrect(m.id, e.target.value); setEditing(false); }} className="mt-2 w-full rounded-lg border border-blue-200 bg-white px-3 py-2.5 font-mono text-[12px] text-ink focus:border-signal focus:outline-none shadow-sm">
              {elements.map((e) => (<option key={e.name} value={e.name}>{e.name} {e.required ? "(required)" : ""}</option>))}
            </select>
          </label>
        </div>
      )}

      {(m.status === "approved" || m.status === "auto") && (
        <p className="mt-4 font-mono text-[10px] font-bold text-ok uppercase tracking-wide">
          ✓ {m.status === "auto" ? "Cleared automatically" : "Approved by you"}
        </p>
      )}
    </div>
  );
}