import type { AgentTraceEvent } from "@/lib/types";

export function LiveActivity({ events }: { events: AgentTraceEvent[] }) {
  const visible = events.slice(-6);
  return (
    <div className="rounded-xl border border-signal/20 bg-white px-4 py-3 shadow-sm">
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-signal">
        MIA is working
      </p>
      <ol className="space-y-1.5">
        {visible.map((event) => (
          <li key={event.id} className="flex gap-2 text-[12px] text-muted">
            <span className="text-signal">↓</span>
            <span>{event.summary}</span>
          </li>
        ))}
        {visible.length === 0 && <li className="text-[12px] text-muted">Starting…</li>}
      </ol>
    </div>
  );
}
