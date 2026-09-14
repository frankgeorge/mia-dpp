"use client";

import { useState } from "react";
import type { CoverageReport, EvidenceRecord, MappingResult, Requirement, RequirementCoverage } from "@/lib/types";

type FactFilter = "attention" | "unresolved" | "review" | "resolved" | "all";
type RequirementFilter = "missing" | "candidate" | "satisfied" | "all";

export function CoveragePanel({ report, evidence, mappingResult }: { report: CoverageReport | null; evidence: EvidenceRecord[]; mappingResult: MappingResult | null }) {
  const [factFilter, setFactFilter] = useState<FactFilter>("attention");
  const [requirementFilter, setRequirementFilter] = useState<RequirementFilter>("missing");
  if (!report) return <p className="mx-auto max-w-sm pt-20 text-center text-[13px] leading-relaxed text-muted">Import a product website to inspect source facts and target coverage.</p>;
  const mappings = [...(mappingResult?.mapped ?? []), ...(mappingResult?.ambiguous ?? [])];
  const mappingByEvidence = new Map(mappings.map((item) => [item.evidenceId, item]));
  const statusOf = (id: string): "unresolved" | "review" | "resolved" => {
    const mapping = mappingByEvidence.get(id);
    if (!mapping) return "unresolved";
    return mapping.status === "review" || mappingResult?.ambiguous.some((item) => item.evidenceId === id) ? "review" : "resolved";
  };
  const visibleFacts = evidence.filter((item) => { const status = statusOf(item.id); return factFilter === "all" || factFilter === status || (factFilter === "attention" && status !== "resolved"); });
  const factCounts = evidence.reduce((counts, item) => ({ ...counts, [statusOf(item.id)]: counts[statusOf(item.id)] + 1 }), { unresolved: 0, review: 0, resolved: 0 });
  const coverageByRequirement = new Map(report.coverage.map((item) => [item.requirementId, item]));
  const evidenceById = new Map(evidence.map((item) => [item.id, item]));
  return <div className="space-y-7">
    <section>
      <div className="flex items-baseline justify-between"><div><p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Source Facts</p><h2 className="mt-1 text-xl font-semibold text-ink">What MIA found</h2></div><span className="font-mono text-sm text-muted">{evidence.length}</span></div>
      <p className="mt-2 text-[12px] text-muted">{factCounts.resolved} resolved · {factCounts.review} review · {factCounts.unresolved} unresolved</p>
      <FilterBar values={["attention", "unresolved", "review", "resolved", "all"]} active={factFilter} onChange={(value) => setFactFilter(value as FactFilter)} />
      <div className="mt-3 space-y-2">
        {visibleFacts.map((fact) => { const status = statusOf(fact.id); const mapping = mappingByEvidence.get(fact.id); return <article key={fact.id} className="rounded-xl border border-hairline bg-paper p-4 shadow-sm"><div className="flex items-start justify-between gap-3"><div><p className="text-[13px] font-semibold text-ink">{fact.sourceLabel ?? fact.predicate}</p><p className="mt-1 text-[13px] text-muted">{displayValue(fact.value)}{fact.unit ? ` ${fact.unit}` : ""}</p></div><StatusPill value={status} /></div><p className="mt-2 truncate font-mono text-[10px] text-muted">{fact.sourceUri}</p>{mapping && <p className="mt-2 text-[11px] text-muted">Current mapping: <span className="font-mono text-signal">{mapping.targetElement}</span></p>}</article>; })}
        {visibleFacts.length === 0 && <p className="rounded-xl border border-dashed border-hairline p-6 text-center text-[12px] text-muted">No source facts match this filter.</p>}
      </div>
    </section>
    <section>
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Submodels</p><p className="mt-1 text-[12px] text-muted">Open a template to inspect its fixed requirements.</p>
      <FilterBar values={["missing", "candidate", "satisfied", "all"]} active={requirementFilter} onChange={(value) => setRequirementFilter(value as RequirementFilter)} />
      <div className="mt-3 space-y-2">{report.inventory.selectedTemplates.map((template) => { const requirements = report.inventory.requirements.filter((item) => item.templateKey === template.key && item.kind === "value" && !item.wildcard); const satisfied = requirements.filter((item) => coverageByRequirement.get(item.id)?.status === "satisfied").length; const visible = requirements.filter((item) => { const status = coverageByRequirement.get(item.id)?.status; if (requirementFilter === "all") return true; if (requirementFilter === "candidate") return status === "candidate" || status === "ambiguous"; return status === requirementFilter; }); return <details key={`${template.key}-${template.release}`} className="rounded-xl border border-hairline bg-paper"><summary className="cursor-pointer list-none px-4 py-3"><div className="flex justify-between gap-3"><span className="text-[13px] font-semibold">{template.family}</span><span className="font-mono text-[11px] text-muted">{satisfied} / {requirements.length}</span></div></summary><div className="space-y-2 border-t border-hairline p-3">{visible.map((requirement) => { const coverage = coverageByRequirement.get(requirement.id); return coverage ? <RequirementCard key={requirement.id} requirement={requirement} coverage={coverage} evidenceById={evidenceById} /> : null; })}{visible.length === 0 && <p className="p-3 text-[12px] text-muted">No requirements match this filter.</p>}</div></details>; })}</div>
    </section>
  </div>;
}

function FilterBar({ values, active, onChange }: { values: string[]; active: string; onChange: (value: string) => void }) { return <div className="mt-3 flex flex-wrap gap-1.5">{values.map((value) => <button key={value} onClick={() => onChange(value)} className={`rounded-full px-3 py-1 text-[11px] capitalize ${active === value ? "bg-ink text-white" : "border border-hairline bg-paper text-muted"}`}>{value === "attention" ? "Unresolved + review" : value}</button>)}</div>; }
function StatusPill({ value }: { value: string }) { return <span className={`rounded-full px-2 py-0.5 font-mono text-[10px] uppercase ${value === "resolved" || value === "satisfied" ? "bg-ok/10 text-ok" : value === "review" || value === "candidate" || value === "ambiguous" ? "bg-warn/10 text-warn" : "bg-mist text-muted"}`}>{value}</span>; }
function RequirementCard({ requirement, coverage, evidenceById }: { requirement: Requirement; coverage: RequirementCoverage; evidenceById: Map<string, EvidenceRecord> }) { const ids = coverage.status === "satisfied" ? coverage.supportingEvidenceIds : coverage.candidateEvidenceIds; return <article className="rounded-lg bg-mist/60 p-3"><div className="flex justify-between gap-3"><div><p className="font-mono text-[12px] font-semibold">{requirement.idShort ?? requirement.templatePath.at(-1)}</p><p className="mt-1 font-mono text-[10px] text-muted">{requirement.templatePath.join(" / ")}</p></div><StatusPill value={coverage.status} /></div>{ids.map((id) => { const item = evidenceById.get(id); return item ? <p key={id} className="mt-2 text-[11px] text-muted">{item.sourceLabel ?? item.predicate}: {displayValue(item.value)}</p> : null; })}<p className="mt-2 text-[11px] text-muted">{coverage.explanation}</p></article>; }
function displayValue(value: unknown): string { return typeof value === "string" ? value : JSON.stringify(value); }
