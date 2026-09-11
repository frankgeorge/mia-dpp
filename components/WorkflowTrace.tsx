import type { WorkflowEvent } from "@/lib/types";

const STAGE_LABELS: Record<string, string> = {
  "source.fetch": "Fetch page",
  "facts.extract": "Extract candidate facts",
  "evidence.normalize": "Normalize evidence",
  "templates.load": "Load target templates",
  "requirements.build": "Build requirement inventory",
  "mapping.deterministic": "Deterministic mapping",
  "coverage.analyze": "Analyze deterministic coverage",
};

export function WorkflowTrace({ events }: { events: WorkflowEvent[] }) {
  if (events.length === 0) {
    return (
      <p className="mx-auto max-w-sm pt-20 text-center text-[13px] leading-relaxed text-muted">
        Import a product website to see each processing stage and its actual
        output count.
      </p>
    );
  }

  return (
    <div className="mx-auto max-w-xl">
      <p className="pb-5 text-[13px] leading-relaxed text-muted">
        This trace records only stages that ran. It is independent of any agent
        or workflow framework.
      </p>
      <ol>
        {events.map((event, index) => (
          <li key={event.id} className="relative flex gap-4 pb-6 last:pb-0">
            {index < events.length - 1 && (
              <span className="absolute left-[11px] top-6 h-full w-px bg-hairline" />
            )}
            <span
              className={`relative z-[1] grid h-6 w-6 shrink-0 place-items-center rounded-full text-[12px] font-semibold ${
                event.status === "done"
                  ? "bg-ok/10 text-ok"
                  : "bg-red-50 text-red-700"
              }`}
              aria-label={event.status}
            >
              {event.status === "done" ? "✓" : "!"}
            </span>
            <div className="min-w-0 flex-1 rounded-xl border border-hairline bg-paper p-4 shadow-sm">
              <div className="flex items-baseline justify-between gap-3">
                <h3 className="text-[13px] font-semibold text-ink">
                  {STAGE_LABELS[event.stage] ?? event.stage}
                </h3>
                <span className="font-mono text-[11px] text-muted">
                  {event.outputCount} output
                  {event.outputCount === 1 ? "" : "s"}
                </span>
              </div>
              <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
                {event.summary}
              </p>
              {event.stage === "mapping.deterministic" && (
                <p className="mt-2 font-mono text-[11px] text-ink/75">
                  {numberMetadata(event.metadata.mapped)} mapped ·{" "}
                  {numberMetadata(event.metadata.ambiguous)} ambiguous ·{" "}
                  {numberMetadata(event.metadata.unmatched)} unmatched
                </p>
              )}
              {event.stage === "coverage.analyze" && (
                <p className="mt-2 font-mono text-[11px] text-ink/75">
                  {numberMetadata(event.metadata.satisfied)} satisfied ·{" "}
                  {numberMetadata(event.metadata.candidate)} candidate ·{" "}
                  {numberMetadata(event.metadata.ambiguous)} ambiguous ·{" "}
                  {numberMetadata(event.metadata.missing)} missing
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function numberMetadata(value: unknown): number {
  return typeof value === "number" ? value : 0;
}
