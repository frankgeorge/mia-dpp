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
    try {
      const [traceRes, artifactsRes] = await Promise.all([
        fetch(`${API_URL}/api/workspaces/${encodeURIComponent(threadId)}/trace`),
        fetch(`${API_URL}/api/workspaces/${encodeURIComponent(threadId)}/artifacts`),
      ]);
      if (traceRes.ok) setEvents((await traceRes.json()) as AgentTraceEvent[]);
      if (artifactsRes.ok) setArtifacts((await artifactsRes.json()) as WorkspaceArtifact[]);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
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
