import type { EvidenceRecord, MappingResult } from "@/lib/types";

type EvidenceOutcome = "mapped" | "ambiguous" | "unmatched";

export function EvidencePanel({
  evidence,
  mappingResult,
}: {
  evidence: EvidenceRecord[];
  mappingResult: MappingResult | null;
}) {
  const outcomes = new Map<string, EvidenceOutcome>();
  mappingResult?.mapped.forEach((mapping) =>
    outcomes.set(mapping.evidenceId, "mapped")
  );
  mappingResult?.ambiguous.forEach((mapping) =>
    outcomes.set(mapping.evidenceId, "ambiguous")
  );
  mappingResult?.unmatchedEvidenceIds.forEach((id) =>
    outcomes.set(id, "unmatched")
  );

  if (evidence.length === 0) {
    return (
      <EmptyEvidence message="Import a product website to inspect every retained source fact." />
    );
  }

  return (
    <div className="space-y-3">
      <p className="pb-1 text-[13px] leading-relaxed text-muted">
        These are source facts, retained before AAS semantics are assigned. An
        unmatched fact is still available for later reasoning or review.
      </p>
      {evidence.map((item) => {
        const outcome = outcomes.get(item.id) ?? "unmatched";
        const location =
          item.sourceLocation.jsonPointer ??
          item.sourceLocation.selector ??
          item.sourceLocation.cell ??
          "source document";
        return (
          <article
            key={item.id}
            className="rounded-xl border border-hairline bg-paper p-4 shadow-sm"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[12px] font-medium text-muted">
                  {item.sourceLabel ?? item.predicate}
                </p>
                <p className="mt-1 break-words text-[14px] font-medium text-ink">
                  {displayValue(item.value)}
                  {item.unit ? ` ${item.unit}` : ""}
                </p>
              </div>
              <OutcomeBadge outcome={outcome} />
            </div>
            <details className="mt-3 border-t border-hairline pt-2">
              <summary className="cursor-pointer text-[11px] font-medium text-muted">
                Provenance
              </summary>
              <dl className="mt-2 grid gap-1 text-[11px] text-muted">
                <div>
                  <dt className="inline font-medium text-ink">Location: </dt>
                  <dd className="inline font-mono">{location}</dd>
                </div>
                <div>
                  <dt className="inline font-medium text-ink">Method: </dt>
                  <dd className="inline font-mono">{item.extractionMethod}</dd>
                </div>
                <div>
                  <dt className="inline font-medium text-ink">Source hash: </dt>
                  <dd className="inline font-mono">
                    {item.sourceContentSha256.slice(0, 16)}…
                  </dd>
                </div>
                <div className="min-w-0">
                  <dt className="inline font-medium text-ink">URL: </dt>
                  <dd className="inline break-all">
                    <a
                      href={item.sourceUri}
                      target="_blank"
                      rel="noreferrer"
                      className="underline underline-offset-2 hover:text-ink"
                    >
                      {item.sourceUri}
                    </a>
                  </dd>
                </div>
              </dl>
            </details>
          </article>
        );
      })}
    </div>
  );
}

function OutcomeBadge({ outcome }: { outcome: EvidenceOutcome }) {
  const classes =
    outcome === "mapped"
      ? "bg-ok/10 text-ok"
      : outcome === "ambiguous"
        ? "bg-warn/10 text-warn"
        : "bg-mist text-muted";
  const label =
    outcome === "mapped"
      ? "Mapped"
      : outcome === "ambiguous"
        ? "Needs review"
        : "Unmatched";
  return (
    <span
      className={`shrink-0 rounded-full px-2 py-1 font-mono text-[10px] ${classes}`}
    >
      {label}
    </span>
  );
}

function EmptyEvidence({ message }: { message: string }) {
  return (
    <p className="mx-auto max-w-sm pt-20 text-center text-[13px] leading-relaxed text-muted">
      {message}
    </p>
  );
}

function displayValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "—";
  return JSON.stringify(value);
}
