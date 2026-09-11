import type {
  CompletionSummary,
  CoverageReport,
  CoverageStatus,
  EvidenceRecord,
  Requirement,
  RequirementCoverage,
} from "@/lib/types";

export function CoveragePanel({
  report,
  evidence,
  completion,
}: {
  report: CoverageReport | null;
  evidence: EvidenceRecord[];
  completion: CompletionSummary | null;
}) {
  if (!report) {
    return (
      <p className="mx-auto max-w-sm pt-20 text-center text-[13px] leading-relaxed text-muted">
        Import a product website to compare retained facts with selected official
        IDTA templates.
      </p>
    );
  }

  const evidenceById = new Map(evidence.map((item) => [item.id, item]));
  const coverageByRequirement = new Map(
    report.coverage.map((item) => [item.requirementId, item])
  );
  return (
    <div className="space-y-6">
      <div>
        <p className="text-[13px] leading-relaxed text-muted">
          Coverage compares source evidence with official template expectations.
          Candidates are not approved mappings.
        </p>
        {completion && (
          <div className="mt-4 space-y-3">
            <SummaryGroup title="Source facts">
              <Counter label="Discovered" value={completion.source.totalDiscovered} />
              <Counter label="Resolved" value={completion.source.automaticallyResolved + completion.source.acceptedAfterReview} tone="ok" />
              <Counter label="Awaiting review" value={completion.source.pendingReview} tone="warn" />
              <Counter label="Unresolved" value={completion.source.unresolved} />
            </SummaryGroup>
            {completion.fixedTemplates.map((template) => (
              <SummaryGroup key={template.templateKey} title={template.templateName}>
                <Counter label="Mandatory filled" value={template.mandatoryFilled} tone="ok" />
                <Counter label="Mandatory total" value={template.mandatoryTotal} />
                <Counter label="Mandatory missing" value={template.mandatoryMissing} tone="danger" />
                <Counter label="Optional filled" value={template.optionalFilled} tone="ok" />
                <Counter label="Optional total" value={template.optionalTotal} />
                <Counter label="Optional missing" value={template.optionalMissing} />
              </SummaryGroup>
            ))}
            <SummaryGroup title="Technical Data">
              <Counter label="Discovered" value={completion.technicalData.discovered} />
              <Counter label="Resolved" value={completion.technicalData.resolved} tone="ok" />
              <Counter label="Unresolved" value={completion.technicalData.unresolved} tone="warn" />
            </SummaryGroup>
          </div>
        )}
      </div>

      {report.inventory.selectedTemplates.map((template) => {
        const requirements = report.inventory.requirements.filter(
          (item) => item.templateKey === template.key
        );
        return (
          <section key={`${template.key}-${template.release}`}>
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
              <div>
                <h2 className="text-[15px] font-semibold text-ink">
                  {template.family}
                </h2>
                <p className="mt-0.5 font-mono text-[11px] text-muted">
                  Release {template.release}
                </p>
              </div>
              <span className="font-mono text-[11px] text-muted">
                {requirements.length} requirements
              </span>
            </div>
            <div className="space-y-3">
              {requirements.map((requirement) => {
                const coverage = coverageByRequirement.get(requirement.id);
                if (!coverage) return null;
                return (
                  <RequirementCard
                    key={requirement.id}
                    requirement={requirement}
                    coverage={coverage}
                    evidenceById={evidenceById}
                  />
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function SummaryGroup({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h2 className="mb-2 text-[12px] font-semibold text-ink">{title}</h2>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">{children}</div>
    </section>
  );
}

function RequirementCard({
  requirement,
  coverage,
  evidenceById,
}: {
  requirement: Requirement;
  coverage: RequirementCoverage;
  evidenceById: Map<string, EvidenceRecord>;
}) {
  const evidenceIds =
    coverage.status === "satisfied"
      ? coverage.supportingEvidenceIds
      : coverage.candidateEvidenceIds;
  const matchedEvidence = evidenceIds.flatMap((id) => {
    const item = evidenceById.get(id);
    return item ? [item] : [];
  });

  return (
    <article
      className="rounded-xl border border-hairline bg-paper p-4 shadow-sm"
      style={{ contentVisibility: "auto", containIntrinsicSize: "0 160px" }}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="break-words font-mono text-[13px] font-semibold text-ink">
            {requirement.idShort ?? requirement.templatePath.at(-1)}
          </h3>
          <p className="mt-1 break-all font-mono text-[10px] leading-relaxed text-muted">
            {requirement.templatePath.join(" / ")}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
          <ObligationBadge requirement={requirement} />
          <StatusBadge status={coverage.status} />
        </div>
      </div>

      {matchedEvidence.length > 0 ? (
        <div className="mt-3 rounded-lg bg-mist/70 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted">
            {coverage.status === "satisfied"
              ? "Supporting evidence"
              : "Possible evidence"}
          </p>
          <ul className="mt-1.5 space-y-1.5">
            {matchedEvidence.map((item) => (
              <li key={item.id} className="text-[12px] leading-relaxed text-ink">
                <span className="font-medium">
                  {item.sourceLabel ?? item.predicate}:
                </span>{" "}
                <span className="break-words text-muted">
                  {displayValue(item.value)}
                  {item.unit ? ` ${item.unit}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="mt-3 text-[12px] text-muted">
          No supporting evidence found.
        </p>
      )}

      <div className="mt-3 border-t border-hairline pt-2 text-[11px] leading-relaxed text-muted">
        <p>
          <span className="font-medium text-ink">Method:</span>{" "}
          <span className="font-mono">{coverage.matchMethod}</span>
        </p>
        <p className="mt-1">{coverage.explanation}</p>
      </div>
    </article>
  );
}

function ObligationBadge({ requirement }: { requirement: Requirement }) {
  const label = requirement.required
    ? "Required"
    : requirement.conditional
      ? "Conditional"
      : "Optional";
  return (
    <span className="rounded-full bg-mist px-2 py-1 font-mono text-[10px] text-muted">
      {label}
    </span>
  );
}

function StatusBadge({ status }: { status: CoverageStatus }) {
  const style =
    status === "satisfied"
      ? "bg-ok/10 text-ok"
      : status === "candidate" || status === "ambiguous"
        ? "bg-warn/10 text-warn"
        : "bg-red-50 text-red-700";
  return (
    <span className={`rounded-full px-2 py-1 font-mono text-[10px] ${style}`}>
      {statusLabel(status)}
    </span>
  );
}

function Counter({
  label,
  value,
  tone = "plain",
}: {
  label: string;
  value: number;
  tone?: "plain" | "ok" | "warn" | "danger";
}) {
  const color =
    tone === "ok"
      ? "text-ok"
      : tone === "warn"
        ? "text-warn"
        : tone === "danger"
          ? "text-red-700"
          : "text-ink";
  return (
    <div className="rounded-xl border border-hairline bg-paper px-3 py-2.5 shadow-sm">
      <p className={`font-mono text-[17px] font-semibold tabular-nums ${color}`}>
        {value}
      </p>
      <p className="mt-0.5 text-[10px] leading-tight text-muted">{label}</p>
    </div>
  );
}

function statusLabel(status: CoverageStatus): string {
  if (status === "satisfied") return "Satisfied";
  if (status === "candidate") return "Candidate";
  if (status === "ambiguous") return "Ambiguous";
  return "Missing";
}

function displayValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "—";
  return JSON.stringify(value);
}
