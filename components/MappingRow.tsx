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
  onCorrect: (
    id: string,
    target: NameplateElement,
    correctedValue?: string
  ) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [targetPath, setTargetPath] = useState(
    m.target.instancePath.join("/")
  );
  const [correctedValue, setCorrectedValue] = useState(m.sourceValue);
  const pct = Math.round(m.confidence * 100);
  const missingPct = Math.max(0, 100 - pct);
  const strong = m.confidence >= 0.85;

  const tone =
    m.status === "rejected"
      ? "opacity-45"
      : m.status === "review"
      ? "border-warn/35"
      : "border-hairline";

  return (
    <div className={`rounded-xl border bg-paper p-4 transition-all duration-300 shadow-sm hover:shadow-md hover:-translate-y-0.5 ${tone}`}>
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

      <details className="mt-2.5 rounded-lg border border-hairline bg-mist/60 px-3 py-2">
        <summary className="cursor-pointer text-[12px] font-medium text-ink">
          Why {pct}%? {missingPct > 0 && `What is the missing ${missingPct}%?`}
        </summary>
        <div className="mt-2.5 space-y-2.5">
          {m.confidenceAssessment.factors.map((factor) => (
            <div key={factor.code}>
              <div className="flex items-baseline justify-between gap-3">
                <p className="text-[12px] font-medium">{factor.label}</p>
                <p className="shrink-0 font-mono text-[10px] text-muted">
                  +{Math.round(factor.awarded * 100)} / {Math.round(factor.maximum * 100)}
                </p>
              </div>
              <p className="mt-0.5 text-[11px] leading-relaxed text-muted">
                {factor.explanation}
              </p>
            </div>
          ))}

          <div className="border-t border-hairline pt-2">
            <p className="text-[11px] font-medium text-ink">
              Remaining uncertainty
            </p>
            {m.confidenceAssessment.remainingUncertainty.length > 0 ? (
              <ul className="mt-1 list-disc space-y-1 pl-4 text-[11px] leading-relaxed text-muted">
                {m.confidenceAssessment.remainingUncertainty.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-[11px] text-muted">
                No missing points under the current deterministic rules.
              </p>
            )}
            <p className="mt-1.5 text-[10px] leading-relaxed text-muted">
              This score explains available evidence; it is not a probability.
            </p>
          </div>
        </div>
      </details>

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
            Correct
          </button>
          <button
            onClick={() => onDecide(m.id, "rejected")}
            className="px-1 text-[12px] text-muted transition-colors hover:text-ink"
          >
            Reject
          </button>
        </div>
      )}

      {editing && (
        <div className="mt-3 space-y-2">
          <label className="text-[12px] text-muted">
            Map this field to
            <select
              autoFocus
              value={targetPath}
              onChange={(e) => setTargetPath(e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-hairline bg-paper px-3 py-2 font-mono text-[12px] focus:border-signal focus:outline-none"
            >
              {elements.map((e) => (
                <option
                  key={e.target.instancePath.join("/")}
                  value={e.target.instancePath.join("/")}
                >
                  {e.path.join(" / ")}
                  {e.required ? " (required)" : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-[12px] text-muted">
            Corrected value
            <input
              value={correctedValue}
              onChange={(event) => setCorrectedValue(event.target.value)}
              className="mt-1.5 w-full rounded-lg border border-hairline bg-paper px-3 py-2 text-[12px] text-ink focus:border-signal focus:outline-none"
            />
          </label>
          <div className="flex gap-2">
            <button
              onClick={() => {
                const target = elements.find(
                  (element) =>
                    element.target.instancePath.join("/") === targetPath
                );
                if (target) onCorrect(m.id, target, correctedValue);
                setEditing(false);
              }}
              className="rounded-full bg-ink px-3 py-1.5 text-[12px] font-medium text-white"
            >
              Save correction
            </button>
            <button
              onClick={() => setEditing(false)}
              className="px-2 text-[12px] text-muted"
            >
              Cancel
            </button>
          </div>
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
