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
  onDecide: (id: string, status: "approved" | "rejected", comment?: string) => void;
  onCorrect: (
    id: string,
    target: NameplateElement,
    correctedValue?: string,
    comment?: string
  ) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [targetPath, setTargetPath] = useState(
    m.target.instancePath.join("/")
  );
  const [correctedValue, setCorrectedValue] = useState(m.sourceValue);
  const [comment, setComment] = useState("");
  const basis = m.assessment.basis[0].toUpperCase() + m.assessment.basis.slice(1);

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
        <span className={`shrink-0 rounded-full px-2 py-0.5 font-mono text-[11px] ${m.assessment.reviewRequired ? "bg-warn/10 text-warn" : "bg-signal/10 text-signal"}`}>
          {basis}
        </span>
      </div>

      <p className="mt-2 text-[12px] leading-relaxed text-muted">
        {m.reasoning}
      </p>

      <p className="mt-2 inline-block rounded-full bg-mist px-2 py-0.5 font-mono text-[10px] text-muted">
        {m.mappingOrigin === "semantic_agent"
          ? "AI-assisted proposal"
          : m.mappingOrigin === "human"
            ? "Human supplied/corrected"
            : "Deterministic mapping"}
        {m.humanReviewed ? " · reviewed" : ""}
      </p>

      {m.llmReview && (
        <div className="mt-3 rounded-lg border border-signal/15 bg-signal/5 p-3 text-[11px] leading-relaxed">
          <p className="font-semibold text-ink">LLM Review</p>
          <p className="mt-1"><span className="font-medium">Conclusion:</span> {m.llmReview.conclusion}</p>
          <p className="mt-1 text-muted"><span className="font-medium text-ink">Why:</span> {m.llmReview.rationale}</p>
          {m.llmReview.uncertainties.length > 0 && <p className="mt-1 text-muted"><span className="font-medium text-ink">Uncertainty:</span> {m.llmReview.uncertainties.join(" · ")}</p>}
        </div>
      )}

      <details className="mt-2.5 rounded-lg border border-hairline bg-mist/60 px-3 py-2">
        <summary className="cursor-pointer text-[12px] font-medium text-ink">
          Why this mapping?
        </summary>
        <div className="mt-2 space-y-2">
          <p className="text-[11px] leading-relaxed text-muted">{m.assessment.reason}</p>
          {m.assessment.uncertainties.length > 0 && (
            <div className="border-t border-hairline pt-2">
              <p className="text-[11px] font-medium text-ink">Requires review because</p>
              <ul className="mt-1 list-disc space-y-1 pl-4 text-[11px] leading-relaxed text-muted">
                {m.assessment.uncertainties.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </details>

      {m.fromGraph && (
        <p className="mt-1.5 inline-block rounded-full bg-signalDim px-2 py-0.5 font-mono text-[10px] text-signal">
          From Integration Graph
        </p>
      )}

      {/* Approval gate */}
      {m.status === "review" && !editing && (
        <div className="mt-3 space-y-2">
          <input value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Optional comment for this decision" className="w-full rounded-lg border border-hairline bg-paper px-3 py-2 text-[12px]" />
          <div className="flex items-center gap-2">
          <button
            onClick={() => onDecide(m.id, "approved", comment)}
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
            onClick={() => onDecide(m.id, "rejected", comment)}
            className="px-1 text-[12px] text-muted transition-colors hover:text-ink"
          >
            Reject
          </button>
          </div>
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
                if (target) onCorrect(m.id, target, correctedValue, comment);
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
          Rejected · undo
        </button>
      )}
    </div>
  );
}
