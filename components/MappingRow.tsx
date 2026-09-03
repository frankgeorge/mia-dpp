"use client";

import { useState } from "react";
import type { FieldMapping } from "@/lib/types";
import { NAMEPLATE_ELEMENTS } from "@/lib/idta";

export function MappingRow({
  mapping: m,
  onDecide,
  onCorrect,
}: {
  mapping: FieldMapping;
  onDecide: (id: string, status: "approved" | "rejected") => void;
  onCorrect: (id: string, target: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const pct = Math.round(m.confidence * 100);
  const strong = m.confidence >= 0.85;

  const tone =
    m.status === "rejected"
      ? "opacity-45"
      : m.status === "review"
      ? "border-warn/35"
      : "border-hairline";

  return (
    <div className={`rounded-xl border bg-paper p-3.5 transition-all ${tone}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-[13px]">
            <span className="text-muted">{m.sourceField}</span>
            <span className="text-hairline"> &rarr; </span>
            <span className="text-signal">{m.targetElement}</span>
          </p>
          <p className="mt-1 truncate text-[14px]">{m.sourceValue}</p>
        </div>
        <span
          className="shrink-0 font-mono text-[12px] tabular-nums"
          style={{ color: strong ? "#1B8A5A" : "#B8760B" }}
        >
          {pct}%
        </span>
      </div>

      <div className="mt-2.5 h-1 w-full overflow-hidden rounded-full bg-mist">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${pct}%`,
            background: strong ? "#1B8A5A" : "#B8760B",
          }}
        />
      </div>

      <p className="mt-2 text-[12px] leading-relaxed text-muted">
        {m.reasoning}
      </p>

      {m.fromGraph && (
        <p className="mt-1.5 inline-block rounded-full bg-signalDim px-2 py-0.5 font-mono text-[10px] text-signal">
          From Integration Graph
        </p>
      )}

      {/* Approval gate */}
      {m.status === "review" && !editing && (
        <div className="mt-3 flex items-center gap-2">
          <button
            onClick={() => onDecide(m.id, "approved")}
            className="rounded-full bg-ink px-3 py-1.5 text-[12px] font-medium text-white transition-opacity hover:opacity-85"
          >
            Approve
          </button>
          <button
            onClick={() => setEditing(true)}
            className="rounded-full border border-hairline px-3 py-1.5 text-[12px] font-medium transition-colors hover:bg-mist"
          >
            Change target
          </button>
          <button
            onClick={() => onDecide(m.id, "rejected")}
            className="px-1 text-[12px] text-muted transition-colors hover:text-ink"
          >
            Discard
          </button>
        </div>
      )}

      {editing && (
        <div className="mt-3">
          <label className="text-[12px] text-muted">
            Map this field to
            <select
              autoFocus
              defaultValue={m.targetElement}
              onChange={(e) => {
                onCorrect(m.id, e.target.value);
                setEditing(false);
              }}
              className="mt-1.5 w-full rounded-lg border border-hairline bg-paper px-3 py-2 font-mono text-[12px] focus:border-signal focus:outline-none"
            >
              {NAMEPLATE_ELEMENTS.map((e) => (
                <option key={e.name} value={e.name}>
                  {e.name}
                  {e.required ? " (required)" : ""}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {(m.status === "approved" || m.status === "auto") && (
        <p className="mt-2.5 font-mono text-[11px] text-ok">
          {m.status === "auto" ? "Cleared automatically" : "Approved by you"}
        </p>
      )}
      {m.status === "rejected" && (
        <button
          onClick={() => onDecide(m.id, "approved")}
          className="mt-2.5 font-mono text-[11px] text-muted underline underline-offset-2"
        >
          Discarded · undo
        </button>
      )}
    </div>
  );
}
