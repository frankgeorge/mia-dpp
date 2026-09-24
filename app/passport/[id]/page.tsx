import { notFound } from "next/navigation";
import sql from "@/lib/db";
import type { DppPackage } from "@/lib/types";
import { CopyLink } from "./CopyLink";

type JsonObject = Record<string, unknown>;

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function printable(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
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

interface LeafValue {
  path: string[];
  value: string;
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
    return children.flatMap((child, i) => collectLeafValues(child, path, i));
  }
  if (element.modelType === "Range") {
    return [
      {
        path,
        value: `${printable(element.min) || "?"} – ${printable(element.max) || "?"}`,
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
      ? [dpp.submodel.idShort as string]
      : ["Nameplate"];
  return (elements as unknown[])
    .filter(isObject)
    .flatMap((el, i) => collectLeafValues(el, root, i));
}

export default async function PassportPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const rows = await sql`
    SELECT id, product_name, submodel, status, qr_code_b64, passport_url, aas_json, created_at
    FROM passports
    WHERE id = ${id}
    LIMIT 1
  `;

  const record = rows[0];
  if (!record) notFound();

  const dpp = record.aas_json as DppPackage | null;
  const leaves = dpp ? artifactLeaves(dpp) : [];
  const productName = record.product_name as string;
  const submodel = record.submodel as string;
  const qrCodeB64 = record.qr_code_b64 as string | null;
  const passportUrl =
    (record.passport_url as string | null) ??
    `https://mia-dpp.vercel.app/passport/${id}`;
  const issuedAt = new Date(record.created_at as string).toLocaleDateString(
    "en-GB",
    { year: "numeric", month: "long", day: "numeric" }
  );

  return (
    <div className="min-h-screen bg-mist">
      {/* Header */}
      <header className="border-b border-hairline bg-paper">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2.5">
            <div className="grid h-7 w-7 place-items-center rounded-lg bg-ink">
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                <path
                  d="M3 8h10M8 3l5 5-5 5"
                  stroke="white"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <span className="text-[14px] font-semibold tracking-tight text-ink">MIA</span>
          </div>
          <span className="rounded-full border border-hairline px-3 py-1 font-mono text-[11px] text-muted">
            Digital Product Passport
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-3xl space-y-5 px-6 py-10">
        {/* Hero card */}
        <div className="rounded-2xl border border-hairline bg-paper p-8 shadow-sm">
          <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
            {/* Product identity */}
            <div className="min-w-0 flex-1">
              <p className="font-mono text-[11px] uppercase tracking-widest text-muted">
                {submodel}
              </p>
              <h1 className="mt-2 text-[26px] font-bold leading-tight tracking-tight text-ink">
                {productName}
              </h1>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-ok/10 px-3 py-1 text-[12px] font-medium text-ok">
                  EU ESPR Compliant
                </span>
                <span className="text-[12px] text-muted">Issued {issuedAt}</span>
              </div>
              <p className="mt-4 font-mono text-[11px] text-muted/50">ID: {id}</p>
            </div>

            {/* QR code */}
            {qrCodeB64 && (
              <div className="shrink-0 text-center">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`data:image/png;base64,${qrCodeB64}`}
                  alt="Passport QR Code"
                  width={160}
                  height={160}
                  className="rounded-xl border border-hairline shadow-sm"
                  style={{ imageRendering: "pixelated" }}
                />
                <p className="mt-2 text-[11px] text-muted">Scan to share</p>
              </div>
            )}
          </div>

          {/* Share bar */}
          <div className="mt-6 flex items-center gap-3 rounded-xl border border-hairline bg-mist p-3">
            <span className="min-w-0 flex-1 truncate font-mono text-[12px] text-ink">
              {passportUrl}
            </span>
            <div className="flex shrink-0 gap-2">
              <CopyLink url={passportUrl} />
              <a
                href={passportUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-full border border-signal/30 bg-signalDim px-4 py-2 text-[13px] font-medium text-signal transition-colors hover:bg-signal/15"
              >
                Open
              </a>
            </div>
          </div>
        </div>

        {/* Product data fields */}
        {leaves.length > 0 && (
          <div className="overflow-hidden rounded-2xl border border-hairline bg-paper shadow-sm">
            <div className="border-b border-hairline px-6 py-4">
              <h2 className="text-[15px] font-semibold text-ink">Product Data</h2>
              <p className="mt-0.5 text-[13px] text-muted">
                Standardised fields · IDTA 02006 Digital Nameplate
              </p>
            </div>
            <div className="divide-y divide-hairline">
              {leaves.map((leaf, i) => (
                <div
                  key={`${leaf.path.join("/")}-${i}`}
                  className="flex items-baseline justify-between gap-6 px-6 py-3"
                >
                  <span className="shrink-0 font-mono text-[11px] text-muted">
                    {leaf.path.at(-1)}
                  </span>
                  <span className="min-w-0 break-words text-right text-[13px] text-ink">
                    {leaf.value}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Verification strip */}
        {dpp && (
          <div className="rounded-xl border border-hairline bg-paper px-6 py-4">
            <div className="flex items-center gap-2">
              <div
                className={`h-2 w-2 rounded-full ${
                  dpp.validationReport.valid ? "bg-ok" : "bg-warn"
                }`}
              />
              <p className="text-[13px] font-medium text-ink">
                {dpp.validationReport.valid
                  ? "Template validation passed"
                  : "Template validation — warnings present"}
              </p>
            </div>
            <p className="mt-2 break-all font-mono text-[10px] text-muted">
              SHA-256 {dpp.artifactSha256}
            </p>
          </div>
        )}

        {/* Footer */}
        <p className="pb-6 text-center text-[12px] text-muted">
          Generated by{" "}
          <a
            href="https://mia-dpp.vercel.app"
            className="text-signal underline underline-offset-2"
          >
            MIA
          </a>{" "}
          · EU ESPR Digital Product Passport · IDTA 02006
        </p>
      </main>
    </div>
  );
}
