"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { AgentActivity } from "@/components/AgentActivity";
import { WorkspaceExplorer } from "@/components/WorkspaceExplorer";
import type { AgentTraceEvent, WorkspaceArtifact } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_MIA_API_URL ?? "";

type Tab = "process" | "data";

const TABS: { id: Tab; label: string }[] = [
  { id: "process", label: "Agent Process" },
  { id: "data", label: "Artifacts" },
];

function ActivityContent() {
  const params = useSearchParams();
  const threadId = params.get("thread");

  const [tab, setTab] = useState<Tab>("process");
  const [events, setEvents] = useState<AgentTraceEvent[]>([]);
  const [artifacts, setArtifacts] = useState<WorkspaceArtifact[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!threadId) return;
    setLoading(true);

    // ── Trace events: read from localStorage first (persisted from workspace) ──
    try {
      const stored = localStorage.getItem(`mia_trace_${threadId}`);
      if (stored) {
        const parsed = JSON.parse(stored) as AgentTraceEvent[];
        if (parsed.length > 0) setEvents(parsed);
      }
    } catch { /* storage not available */ }

    try {
      // Try backend SQLite (works when same container instance, or with persistent volume)
      const traceRes = await fetch(`${API_URL}/api/workspaces/${encodeURIComponent(threadId)}/trace`);
      if (traceRes.ok) {
        const apiEvents = (await traceRes.json()) as AgentTraceEvent[];
        if (apiEvents.length > 0) {
          // Backend has more events — merge with localStorage copy
          setEvents((prev) => {
            const existingIds = new Set(prev.map((e) => e.id));
            const merged = [...prev, ...apiEvents.filter((e) => !existingIds.has(e.id))];
            // Also update localStorage with the merged set
            try { localStorage.setItem(`mia_trace_${threadId}`, JSON.stringify(merged)); } catch { /* ignore */ }
            return merged;
          });
        }
      }

      // ── Artifacts: try backend, fall back to passport registry ──
      const artifactsRes = await fetch(`${API_URL}/api/workspaces/${encodeURIComponent(threadId)}/artifacts`);
      let backendArtifacts: WorkspaceArtifact[] = [];
      if (artifactsRes.ok) {
        backendArtifacts = (await artifactsRes.json()) as WorkspaceArtifact[];
      }

      if (backendArtifacts.length > 0) {
        setArtifacts(backendArtifacts);
      } else {
        // Backend has no artifacts (different container / cold start).
        // Build a synthetic entry from the passport stored in Supabase.
        const passportRes = await fetch(`/api/passports/thread/${encodeURIComponent(threadId)}`);
        if (passportRes.ok) {
          const passport = await passportRes.json() as {
            product_name?: string;
            aas_json?: unknown;
            passport_url?: string | null;
            updated_at?: string;
          };
          if (passport.aas_json) {
            const synthetic: WorkspaceArtifact = {
              id: `passport-aas-${threadId}`,
              kind: "aas",
              name: `${(passport.product_name ?? "passport").replace(/[^a-z0-9]/gi, "_").toLowerCase()}-dpp.json`,
              relativePath: `aas/passport-${threadId}.json`,
              createdAt: passport.updated_at ?? new Date().toISOString(),
              createdBy: "mia",
              contentType: "application/json",
              sha256: "",
              size: JSON.stringify(passport.aas_json).length,
              productId: null,
              sourceUrl: passport.passport_url ?? null,
              derivedFrom: [],
              downloadable: true,
            };
            setArtifacts([synthetic]);
          }
        }
      }
    } catch { /* ignore network errors */ }

    setLoading(false);
  }, [threadId]);

  useEffect(() => { void load(); }, [load]);

  if (!threadId) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <p className="text-[15px] font-semibold text-ink">No session selected</p>
          <p className="mt-1 text-[13px] text-muted">Open this page from the workspace via the &ldquo;Agent activity&rdquo; link.</p>
          <a href="/workspace" className="mt-4 inline-block rounded-full bg-ink px-5 py-2 text-[13px] font-medium text-white">
            Back to workspace
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-hairline bg-paper px-6">
        <div className="flex items-center gap-3">
          <a href="/workspace" className="text-[13px] text-muted hover:text-ink">← Workspace</a>
          <span className="text-muted">/</span>
          <span className="text-[13px] font-medium text-ink">Agent Activity</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-muted">{threadId}</span>
          <button
            onClick={() => void load()}
            className="rounded-full border border-hairline px-3 py-1 text-[12px] text-muted hover:text-ink"
          >
            Refresh
          </button>
        </div>
      </header>

      {/* Tabs */}
      <div className="flex shrink-0 border-b border-hairline bg-paper px-4">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`relative px-4 py-3 text-[12px] font-medium transition-colors ${
              tab === t.id ? "text-signal" : "text-muted hover:text-ink"
            }`}
          >
            {t.label}
            {t.id === "process" && events.length > 0 && (
              <span className="ml-1 rounded-full bg-mist px-1.5 py-0.5 font-mono text-[10px] text-ink">{events.length}</span>
            )}
            {t.id === "data" && artifacts.length > 0 && (
              <span className="ml-1 rounded-full bg-mist px-1.5 py-0.5 font-mono text-[10px] text-ink">{artifacts.length}</span>
            )}
            {tab === t.id && (
              <span className="absolute inset-x-2 -bottom-px h-[2px] rounded-t-full bg-signal" />
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="scroll-quiet min-h-0 flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="flex gap-1.5">
              {[0, 1, 2].map((i) => (
                <span key={i} className="h-2 w-2 animate-pulse rounded-full bg-muted" style={{ animationDelay: `${i * 150}ms` }} />
              ))}
            </div>
          </div>
        ) : tab === "process" ? (
          <AgentActivity events={events} />
        ) : (
          <WorkspaceExplorer apiUrl={API_URL} threadId={threadId} artifacts={artifacts} />
        )}
      </div>
    </div>
  );
}

export default function ActivityPage() {
  return (
    <Suspense fallback={
      <div className="flex h-full items-center justify-center">
        <div className="flex gap-1.5">
          {[0, 1, 2].map((i) => (
            <span key={i} className="h-2 w-2 animate-pulse rounded-full bg-muted" style={{ animationDelay: `${i * 150}ms` }} />
          ))}
        </div>
      </div>
    }>
      <ActivityContent />
    </Suspense>
  );
}
