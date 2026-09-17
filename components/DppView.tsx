"use client";

import { useState } from "react";
import type { DppPackage, Severity } from "@/lib/types";

type JsonObject = Record<string, unknown>;

interface LeafValue {
  path: string[];
  value: string;
}

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function printable(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (
    Array.isArray(value) &&
    value.every(
      (item) =>
        isObject(item) &&
        typeof item.language === "string" &&
        typeof item.text === "string"
    )
  ) {
    return value
      .map((item) => `${String(item.language)}: ${String(item.text)}`)
      .join(" · ");
  }
  return JSON.stringify(value);
}

function nestedElements(element: JsonObject): JsonObject[] {
  const modelType = element.modelType;
  const childKey =
    modelType === "SubmodelElementCollection" ||
    modelType === "SubmodelElementList"
      ? "value"
      : modelType === "Entity"
      ? "statements"
      : modelType === "AnnotatedRelationshipElement"
      ? "annotations"
      : null;
  const children = childKey ? element[childKey] : null;
  if (!Array.isArray(children)) return [];
  return children.filter(isObject);
}

function collectLeafValues(
  element: JsonObject,
  parentPath: string[],
  index: number
): LeafValue[] {
  const segment =
    typeof element.idShort === "string" && element.idShort
      ? element.idShort
      : `[${index + 1}]`;
  const path = [...parentPath, segment];
  const children = nestedElements(element);
  if (children.length > 0) {
    return children.flatMap((child, childIndex) =>
      collectLeafValues(child, path, childIndex)
    );
  }

  if (element.modelType === "Range") {
    return [
      {
        path,
        value: `${printable(element.min) || "?"} – ${
          printable(element.max) || "?"
        }`,
      },
    ];
  }
  if ("value" in element) {
    return [{ path, value: printable(element.value) }];
  }
  return [];
}

function artifactLeaves(dpp: DppPackage): LeafValue[] {
  const elements = dpp.submodel.submodelElements;
  if (!Array.isArray(elements)) return [];
  const root =
    typeof dpp.submodel.idShort === "string"
      ? [dpp.submodel.idShort]
      : ["Submodel"];
  return elements
    .filter(isObject)
    .flatMap((element, index) => collectLeafValues(element, root, index));
}

function severityTone(severity: Severity): string {
  if (severity === "error") return "text-warn";
  if (severity === "warning") return "text-warn";
  return "text-muted";
}

export function DppView({ dpp }: { dpp: DppPackage }) {
  const [showJson, setShowJson] = useState(false);
  const json = JSON.stringify(dpp.environment, null, 2);
  const leaves = artifactLeaves(dpp);
  const gapCount = dpp.gapReport.gaps.length;
  const findingCount = dpp.validationReport.findings.length;

  function download() {
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${dpp.passportId.replace(/[:]/g, "_")}.environment.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="mt-5 overflow-hidden rounded-2xl border border-hairline bg-paper">
      <div className="border-b border-hairline bg-ink px-5 py-4 text-white">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-white/50">
              AAS environment
            </p>
            <p className="mt-1.5 text-[17px] font-semibold tracking-tight">
              {dpp.productName}
            </p>
          </div>
          <span
            className={`shrink-0 rounded-full px-2.5 py-1 font-mono text-[10px] ${
              dpp.deployable
                ? "bg-ok/20 text-white"
                : "bg-warn/25 text-white"
            }`}
          >
            {dpp.deployable ? "Deployable" : "Deployment blocked"}
          </span>
        </div>
        <p className="mt-1 break-all font-mono text-[11px] text-white/45">
          {dpp.passportId}
        </p>
      </div>

      <div className="grid gap-px border-b border-hairline bg-hairline sm:grid-cols-3">
        <Summary
          label="Template"
          value={`${dpp.template.family} ${dpp.template.release}`}
        />
        <Summary
          label="Validation"
          value={dpp.validationReport.valid ? "Passed" : "Failed"}
          ok={dpp.validationReport.valid}
        />
        <Summary
          label="Template gaps"
          value={gapCount === 0 ? "None" : String(gapCount)}
          ok={!dpp.gapReport.blocksDeployment}
        />
      </div>

      <div className="divide-y divide-hairline">
        {leaves.length === 0 ? (
          <p className="px-5 py-4 text-[13px] text-muted">
            The compiled submodel contains no displayable leaf values.
          </p>
        ) : (
          leaves.map((leaf, index) => (
            <div
              key={`${leaf.path.join("/")}-${index}`}
              className="flex items-baseline justify-between gap-4 px-5 py-2.5"
            >
              <span className="min-w-0 break-words font-mono text-[11px] text-muted">
                {leaf.path.join(" / ")}
              </span>
              <span className="max-w-[45%] break-words text-right text-[13px]">
                {leaf.value}
              </span>
            </div>
          ))
        )}
      </div>

      <div className="border-t border-hairline px-5 py-4">
        <p
          className={`text-[13px] font-medium ${
            dpp.gapReport.blocksDeployment ? "text-warn" : "text-ok"
          }`}
        >
          {dpp.gapReport.blocksDeployment
            ? "Required template information is missing"
            : "No blocking template gaps"}
        </p>
        {gapCount > 0 && (
          <ul className="mt-2 space-y-1.5">
            {dpp.gapReport.gaps.map((gap, index) => (
              <li
                key={`${gap.templatePath.join("/")}-${index}`}
                className={`text-[12px] leading-relaxed ${severityTone(
                  gap.severity
                )}`}
              >
                <span className="font-mono">
                  {gap.templatePath.join(" / ") || "Template"}
                </span>{" "}
                — {gap.message}
              </li>
            ))}
          </ul>
        )}
      </div>

      {findingCount > 0 && (
        <details className="border-t border-hairline px-5 py-4">
          <summary className="cursor-pointer text-[13px] font-medium">
            Validation findings ({findingCount})
          </summary>
          <ul className="mt-2 space-y-2">
            {dpp.validationReport.findings.map((finding, index) => (
              <li
                key={`${finding.code}-${index}`}
                className={`text-[12px] leading-relaxed ${severityTone(
                  finding.severity
                )}`}
              >
                <span className="font-mono">{finding.code}</span> —{" "}
                {finding.message}
                {(finding.instancePath.length > 0 ||
                  finding.templatePath.length > 0) && (
                  <span className="mt-0.5 block font-mono text-[10px] text-muted">
                    {(finding.instancePath.length > 0
                      ? finding.instancePath
                      : finding.templatePath
                    ).join(" / ")}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}

      {dpp.evidence.length > 0 && (
        <details className="border-t border-hairline px-5 py-4">
          <summary className="cursor-pointer text-[13px] font-medium">
            Source provenance ({dpp.evidence.length})
          </summary>
          <ul className="mt-3 space-y-3">
            {dpp.evidence.map((record) => (
              <li key={record.id} className="text-[11px] leading-relaxed">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="font-mono text-ink">{record.predicate}</span>
                  <span className="text-muted">{record.extractionMethod}</span>
                </div>
                <p className="mt-0.5 break-words text-[12px]">
                  {printable(record.value)}
                </p>
                {record.sourceUri.startsWith("http") ? (
                  <a
                    href={record.sourceUri}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-0.5 block break-all text-signal underline underline-offset-2"
                  >
                    {record.sourceUri}
                  </a>
                ) : (
                  <p className="mt-0.5 break-all text-muted">
                    {record.sourceUri}
                  </p>
                )}
                {(record.sourceLocation.jsonPointer ||
                  record.sourceLocation.selector) && (
                  <p className="mt-0.5 font-mono text-[10px] text-muted">
                    {record.sourceLocation.jsonPointer ??
                      record.sourceLocation.selector}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-hairline p-4">
        <button
          onClick={download}
          className="rounded-full bg-signal px-4 py-2 text-[13px] font-medium text-white transition-opacity hover:opacity-88"
        >
          Download AAS environment
        </button>
        <button
          onClick={() => setShowJson((shown) => !shown)}
          className="rounded-full border border-hairline px-4 py-2 text-[13px] font-medium transition-colors hover:bg-mist"
        >
          {showJson ? "Hide" : "View"} environment JSON
        </button>
        <span className="ml-auto font-mono text-[11px] text-muted">
          {leaves.length} leaf value{leaves.length === 1 ? "" : "s"}
        </span>
      </div>

      <div className="border-t border-hairline px-5 py-3 font-mono text-[10px] text-muted">
        SHA-256 {dpp.artifactSha256}
      </div>

      {showJson && (
        <pre className="scroll-quiet max-h-72 overflow-auto border-t border-hairline bg-mist p-4 font-mono text-[11px] leading-relaxed">
          {json}
        </pre>
      )}
    </div>
  );
}

function Summary({
  label,
  value,
  ok,
}: {
  label: string;
  value: string;
  ok?: boolean;
}) {
  return (
    <div className="bg-paper px-4 py-3">
      <p className="font-mono text-[10px] uppercase tracking-wide text-muted">
        {label}
      </p>
      <p
        className={`mt-1 truncate text-[12px] font-medium ${
          ok === undefined ? "text-ink" : ok ? "text-ok" : "text-warn"
        }`}
        title={value}
      >
        {value}
      </p>
    </div>
  );
}
