"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

type AgentType = "carbon_footprint" | "technical_data";

interface ExtractedField {
  idta_field: string;
  value: string;
  confidence?: number;
  source_excerpt?: string;
}

interface AgentRun {
  id: string;
  thread_id: string;
  product_name: string;
  agent_type: AgentType;
  reply: string;
  methodology: string;
  confidence: string;
  data_sources: string[];
  extracted_fields: ExtractedField[];
  field_count: number;
  tool_calls: Array<{ tool: string; input: string; success: string; summary: string }>;
  calculation_inputs: Record<string, string>;
  created_at: string;
}

const AGENT_META: Record<AgentType, { label: string; standard: string; icon: string; badge: string }> = {
  carbon_footprint: {
    label: "Carbon Footprint",
    standard: "IDTA 02023",
    icon: "🌿",
    badge: "bg-ok/10 text-ok",
  },
  technical_data: {
    label: "Technical Data",
    standard: "IDTA 02003",
    icon: "⚙️",
    badge: "bg-signal/10 text-signal",
  },
};

const CONFIDENCE_BADGE: Record<string, string> = {
  verified: "bg-ok/10 text-ok",
  high:     "bg-ok/10 text-ok",
  medium:   "bg-warn/10 text-warn",
  low:      "bg-error/10 text-error",
  estimated:"bg-muted/10 text-muted",
};

export default function AgentsPage() {
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | AgentType>("all");
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/agent-runs")
      .then((r) => r.json())
      .then((data) => {
        setRuns(Array.isArray(data) ? data : []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const filtered = filter === "all" ? runs : runs.filter((r) => r.agent_type === filter);

  return (
    <div className="px-8 py-8">
      <div className="mx-auto max-w-shell">
        {/* Header */}
        <div className="mb-8 flex items-start justify-between gap-4">
          <div>
            <h1 className="text-[22px] font-semibold tracking-tight text-ink">Agent Runs</h1>
            {!loading && runs.length > 0 && (
              <p className="mt-1 text-[13px] text-muted">
                {runs.length} run{runs.length !== 1 ? "s" : ""} &mdash; full audit trail of every AI agent execution
              </p>
            )}
          </div>
          <Link
            href="/workspace"
            className="flex shrink-0 items-center gap-2 rounded-full bg-ink px-4 py-2 text-[13px] font-medium text-white transition-all hover:-translate-y-px hover:shadow-md"
          >
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
              <path d="M6.5 1v11M1 6.5h11" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
            New passport
          </Link>
        </div>

        {/* Filter tabs */}
        {!loading && runs.length > 0 && (
          <div className="mb-4 flex gap-1 rounded-xl border border-hairline bg-mist p-1 w-fit">
            {(["all", "carbon_footprint", "technical_data"] as const).map((f) => {
              const label = f === "all" ? "All" : AGENT_META[f].label;
              const count = f === "all" ? runs.length : runs.filter((r) => r.agent_type === f).length;
              return (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-medium transition-colors ${
                    filter === f ? "bg-paper text-ink shadow-sm" : "text-muted hover:text-ink"
                  }`}
                >
                  {label}
                  <span className={`rounded-full px-1.5 py-0.5 text-[10px] tabular-nums ${
                    filter === f ? "bg-mist text-muted" : "bg-muted/10 text-muted"
                  }`}>
                    {count}
                  </span>
                </button>
              );
            })}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex min-h-[400px] items-center justify-center">
            <div className="flex gap-1.5">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="h-2 w-2 animate-pulse rounded-full bg-muted"
                  style={{ animationDelay: `${i * 150}ms` }}
                />
              ))}
            </div>
          </div>
        )}

        {/* Empty state */}
        {!loading && runs.length === 0 && (
          <div className="flex min-h-[400px] items-center justify-center rounded-2xl border border-hairline bg-paper">
            <div className="max-w-xs px-8 py-12 text-center">
              <div className="mx-auto mb-5 grid h-14 w-14 place-items-center rounded-2xl border border-hairline bg-mist text-2xl">
                🤖
              </div>
              <p className="text-[16px] font-semibold text-ink">No agent runs yet</p>
              <p className="mt-2 text-[13px] leading-relaxed text-muted">
                Runs are recorded automatically when you trigger the Carbon Footprint or Technical Data agent from a chat.
              </p>
              <Link
                href="/workspace"
                className="mt-5 inline-flex items-center gap-2 rounded-full bg-ink px-5 py-2.5 text-[13px] font-medium text-white transition-all hover:-translate-y-px hover:shadow-md"
              >
                Open chat
              </Link>
            </div>
          </div>
        )}

        {/* Runs list */}
        {!loading && filtered.length > 0 && (
          <div className="space-y-2">
            {filtered.map((run) => (
              <RunRow
                key={run.id}
                run={run}
                isExpanded={expanded === run.id}
                onToggle={() => setExpanded(expanded === run.id ? null : run.id)}
              />
            ))}
          </div>
        )}

        {/* Empty filter result */}
        {!loading && runs.length > 0 && filtered.length === 0 && (
          <p className="py-12 text-center text-[13px] text-muted">No runs of this type yet.</p>
        )}
      </div>
    </div>
  );
}

function RunRow({
  run,
  isExpanded,
  onToggle,
}: {
  run: AgentRun;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const meta = AGENT_META[run.agent_type] ?? {
    label: run.agent_type,
    standard: "",
    icon: "🤖",
    badge: "bg-muted/10 text-muted",
  };

  const confidenceBadge = CONFIDENCE_BADGE[run.confidence] ?? CONFIDENCE_BADGE.estimated;

  const date = new Date(run.created_at).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  const time = new Date(run.created_at).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className="rounded-2xl border border-hairline bg-paper overflow-hidden transition-shadow hover:shadow-sm">
      {/* Collapsed row */}
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-4 p-4 text-left"
      >
        {/* Agent icon */}
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-hairline bg-mist text-[18px]">
          {meta.icon}
        </div>

        {/* Product + badges */}
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[14px] font-semibold text-ink truncate">{run.product_name}</p>
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${meta.badge}`}>
              {meta.label}
            </span>
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize ${confidenceBadge}`}>
              {run.confidence}
            </span>
          </div>
          <p className="mt-0.5 font-mono text-[11px] text-muted">{meta.standard}</p>
        </div>

        {/* Stats */}
        <div className="hidden sm:flex items-center gap-6 shrink-0">
          <div className="text-right">
            <p className="text-[14px] font-semibold text-ink">{run.field_count}</p>
            <p className="text-[10px] text-muted">fields</p>
          </div>
          <div className="text-right">
            <p className="text-[12px] text-ink">{date}</p>
            <p className="text-[10px] text-muted">{time}</p>
          </div>
        </div>

        {/* Chevron */}
        <svg
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="none"
          className={`shrink-0 text-muted transition-transform ${isExpanded ? "rotate-180" : ""}`}
        >
          <path
            d="M4 6l4 4 4-4"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      {/* Expanded detail */}
      {isExpanded && (
        <div className="border-t border-hairline px-4 py-4 space-y-4">
          {/* Summary */}
          {run.reply && (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted mb-1">Summary</p>
              <p className="text-[13px] text-ink leading-relaxed">{run.reply}</p>
            </div>
          )}

          {/* Methodology */}
          {run.methodology && (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted mb-1">Methodology</p>
              <p className="text-[13px] text-ink leading-relaxed">{run.methodology}</p>
            </div>
          )}

          {/* Sources */}
          {Array.isArray(run.data_sources) && run.data_sources.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted mb-2">
                Sources ({run.data_sources.length})
              </p>
              <div className="space-y-1">
                {run.data_sources.map((src, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <span className="shrink-0 mt-0.5 font-mono text-[10px] text-muted">{i + 1}.</span>
                    {src.startsWith("http") ? (
                      <a
                        href={src}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[12px] text-signal hover:underline break-all"
                      >
                        {src}
                      </a>
                    ) : (
                      <p className="text-[12px] text-ink break-all">{src}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Calculation Inputs */}
          {Object.keys(run.calculation_inputs ?? {}).length > 0 && (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted mb-2">
                Calculation Inputs
              </p>
              <div className="rounded-xl border border-hairline overflow-hidden">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="border-b border-hairline bg-mist">
                      <th className="px-3 py-2 text-left font-semibold text-muted">Parameter</th>
                      <th className="px-3 py-2 text-left font-semibold text-muted">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(run.calculation_inputs ?? {}).map(([k, v], i, arr) => (
                      <tr key={k} className={i < arr.length - 1 ? "border-b border-hairline" : ""}>
                        <td className="px-3 py-2 font-mono text-signal whitespace-nowrap">{k}</td>
                        <td className="px-3 py-2 text-ink break-all">{String(v)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Agent Trace */}
          {Array.isArray(run.tool_calls) && run.tool_calls.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted mb-2">
                Agent Trace ({run.tool_calls.length} tool call{run.tool_calls.length !== 1 ? "s" : ""})
              </p>
              <div className="space-y-2">
                {run.tool_calls.map((tc, i) => (
                  <div key={i} className="rounded-xl border border-hairline overflow-hidden">
                    <div className="flex items-center gap-2 px-3 py-2 bg-mist border-b border-hairline">
                      <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${tc.success === "true" ? "bg-ok" : "bg-error"}`} />
                      <span className="font-mono text-[11px] font-semibold text-ink">{tc.tool}</span>
                      <span className="text-[11px] text-muted truncate">{tc.input}</span>
                    </div>
                    {tc.summary && (
                      <p className="px-3 py-2 text-[11px] text-muted leading-relaxed line-clamp-3">{tc.summary}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Extracted fields table */}
          {Array.isArray(run.extracted_fields) && run.extracted_fields.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted mb-2">
                Extracted Fields ({run.extracted_fields.length})
              </p>
              <div className="rounded-xl border border-hairline overflow-hidden">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="border-b border-hairline bg-mist">
                      <th className="px-3 py-2 text-left font-semibold text-muted">Field</th>
                      <th className="px-3 py-2 text-left font-semibold text-muted">Value</th>
                      <th className="px-3 py-2 text-right font-semibold text-muted hidden sm:table-cell">Conf.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {run.extracted_fields.map((f, i) => (
                      <tr
                        key={i}
                        className={i < run.extracted_fields.length - 1 ? "border-b border-hairline" : ""}
                      >
                        <td className="px-3 py-2 font-mono text-signal whitespace-nowrap">{f.idta_field}</td>
                        <td className="px-3 py-2 text-ink">{f.value}</td>
                        <td className="px-3 py-2 text-right text-muted hidden sm:table-cell">
                          {f.confidence !== undefined
                            ? `${Math.round(f.confidence * 100)}%`
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Footer */}
          <div className="flex items-center justify-between border-t border-hairline pt-3">
            <p className="font-mono text-[10px] text-muted">{run.id}</p>
            <Link
              href={`/workspace?thread=${run.thread_id}`}
              className="text-[12px] font-medium text-signal hover:underline"
            >
              Open in chat →
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
