import type { MappingKnowledgeEntry } from "@/lib/types";

export function IntegrationGraph({ entries }: { entries: MappingKnowledgeEntry[] }) {
  return <div className="space-y-4">
    <div className="rounded-xl border border-hairline bg-paper p-4">
      <h2 className="text-[14px] font-semibold text-ink">Integration Graph</h2>
      <p className="mt-2 max-w-2xl text-[12px] leading-relaxed text-muted">This contains mapping knowledge learned from reviewed product mappings. It becomes useful after mappings are approved or corrected. Reviewed knowledge can later be used as reference when MIA encounters similar source fields in future products.</p>
      <p className="mt-3 font-mono text-[11px] text-muted">{entries.filter((item) => item.status === "trusted").length} reviewed mapping rules learned</p>
    </div>
    {entries.length === 0 ? <p className="rounded-xl border border-dashed border-hairline p-8 text-center text-[12px] text-muted">Approve or correct a semantic mapping to create trusted reusable knowledge.</p> : entries.map((entry) => <details key={entry.id} className="rounded-xl border border-hairline bg-paper p-4 shadow-sm">
      <summary className="cursor-pointer list-none"><div className="flex items-start justify-between gap-3"><p className="font-mono text-[13px]">{entry.sourceField} <span className="text-muted">→</span> <span className="text-signal">{entry.targetPath.at(-1)}</span></p><span className={`rounded-full px-2 py-0.5 font-mono text-[10px] uppercase ${entry.status === "trusted" ? "bg-ok/10 text-ok" : "bg-warn/10 text-warn"}`}>{entry.status}</span></div><p className="mt-1.5 text-[11px] text-muted">{entry.manufacturer ?? entry.domain ?? "Unscoped"} · Confirmed {entry.confirmations} · Corrections {entry.corrections}</p></summary>
      <div className="mt-3 space-y-2 border-t border-hairline pt-3 text-[11px] text-muted"><p><span className="font-medium text-ink">Target:</span> {entry.targetTemplate} / {entry.targetPath.join(" / ")}</p><p className="break-all"><span className="font-medium text-ink">Semantic ID:</span> {entry.semanticId}</p>{entry.llmReviewSummary && <p><span className="font-medium text-ink">LLM review:</span> {entry.llmReviewSummary}</p>}{entry.exampleValues.length > 0 && <p><span className="font-medium text-ink">Examples:</span> {entry.exampleValues.join(" · ")}</p>}{entry.humanComments.map((comment) => <blockquote key={comment} className="border-l-2 border-signal pl-2">{comment}</blockquote>)}<p>Last reviewed: {new Date(entry.updatedAt).toLocaleString()}</p></div>
    </details>)}
  </div>;
}
