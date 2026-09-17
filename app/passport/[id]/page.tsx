"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import QRCode from "qrcode";
import type { DppPackage } from "@/lib/standards/types";

export default function PassportPage({ params }: { params: { id: string } }) {
  const [dpp, setDpp] = useState<DppPackage | null>(null);
  const [savedAt, setSavedAt] = useState("");
  const [qrDataUrl, setQrDataUrl] = useState("");
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    fetch(`/api/passport?id=${encodeURIComponent(params.id)}`)
      .then((r) => r.json())
      .then(async (data) => {
        if (data.error) {
          setPhase("error");
          return;
        }
        setDpp(data.dpp);
        setSavedAt(data.savedAt);

        // Generate QR code pointing to this page
        const pageUrl = window.location.href;
        const qr = await QRCode.toDataURL(pageUrl, {
          width: 200,
          margin: 2,
          color: { dark: "#17181A", light: "#FFFFFF" },
        });
        setQrDataUrl(qr);
        setPhase("ready");
      })
      .catch(() => setPhase("error"));
  }, [params.id]);

  function downloadQr() {
    if (!qrDataUrl) return;
    const a = document.createElement("a");
    a.href = qrDataUrl;
    a.download = `dpp-qr-${params.id.slice(-8)}.png`;
    a.click();
  }

  function downloadJson() {
    if (!dpp) return;
    const blob = new Blob([JSON.stringify(dpp.submodel, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${dpp.passportId.replace(/[:]/g, "_")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (phase === "loading") {
    return (
      <Shell>
        <div className="flex justify-center pt-24">
          <div className="flex gap-1.5">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="h-2 w-2 animate-pulse rounded-full"
                style={{ background: "#6E6E73", animationDelay: `${i * 140}ms` }}
              />
            ))}
          </div>
        </div>
      </Shell>
    );
  }

  if (phase === "error") {
    return (
      <Shell>
        <div
          className="mx-auto max-w-md rounded-2xl p-10 text-center"
          style={{ border: "1px solid #DCDCE0", background: "#FFFFFF" }}
        >
          <p className="text-[16px] font-semibold" style={{ color: "#17181A" }}>
            Passport not found
          </p>
          <p className="mt-2 text-[14px]" style={{ color: "#6E6E73" }}>
            This passport link may have expired. Generate a new one in the workspace.
          </p>
          <Link
            href="/workspace"
            className="mt-5 inline-block rounded-full px-5 py-2.5 text-[13px] font-semibold text-white"
            style={{ background: "#17181A" }}
          >
            Go to workspace
          </Link>
        </div>
      </Shell>
    );
  }

  const elements = (dpp!.submodel as any).submodelElements ?? [];

  return (
    <Shell>
      <div style={{ maxWidth: 680, margin: "0 auto" }}>
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <Link href="/workspace" className="flex items-center gap-2">
            <span
              className="grid h-6 w-6 place-items-center rounded-md"
              style={{ background: "#17181A" }}
            >
              <span className="rounded-[1px]" style={{ height: 6, width: 6, background: "#fff" }} />
            </span>
            <span className="text-[15px] font-semibold tracking-tight" style={{ color: "#17181A" }}>
              MIA
            </span>
          </Link>
          <span className="font-mono text-[11px]" style={{ color: "#6E6E73" }}>
            Digital Product Passport
          </span>
        </div>

        <div
          className="overflow-hidden rounded-2xl"
          style={{ border: "1px solid #DCDCE0", background: "#FFFFFF" }}
        >
          {/* Passport header */}
          <div className="px-6 py-5" style={{ background: "#17181A" }}>
            <p
              className="font-mono text-[10px] uppercase tracking-[0.18em]"
              style={{ color: "rgba(255,255,255,0.4)" }}
            >
              IDTA Digital Nameplate · {dpp!.passportId.split(":")[2] ?? "product"}
            </p>
            <h1
              className="mt-1.5 text-[20px] font-semibold tracking-tight"
              style={{ color: "#FFFFFF" }}
            >
              {dpp!.productName}
            </h1>
            <p
              className="mt-1 break-all font-mono text-[10px]"
              style={{ color: "rgba(255,255,255,0.35)" }}
            >
              {dpp!.passportId}
            </p>
          </div>

          {/* Fields */}
          <div style={{ borderTop: "1px solid #DCDCE0" }}>
            {elements.map((el: any) => {
              const confidence = el.qualifiers?.find(
                (q: any) => q.type === "MappingConfidence"
              )?.value;
              return (
                <div
                  key={el.idShort}
                  className="flex items-baseline justify-between gap-4 px-6 py-3"
                  style={{ borderBottom: "1px solid #DCDCE0" }}
                >
                  <div className="shrink-0">
                    <span className="font-mono text-[12px]" style={{ color: "#6E6E73" }}>
                      {el.idShort}
                    </span>
                    {confidence && (
                      <span
                        className="ml-2 font-mono text-[10px]"
                        style={{ color: parseFloat(confidence) >= 0.85 ? "#1B8A5A" : "#B8760B" }}
                      >
                        {Math.round(parseFloat(confidence) * 100)}%
                      </span>
                    )}
                  </div>
                  <span
                    className="truncate text-right text-[14px]"
                    style={{ color: "#17181A" }}
                  >
                    {el.value}
                  </span>
                </div>
              );
            })}
          </div>

          {/* QR + actions */}
          <div
            className="flex flex-wrap items-center gap-4 px-6 py-5"
            style={{ borderTop: "1px solid #DCDCE0" }}
          >
            {qrDataUrl && (
              <div className="flex flex-col items-center gap-2">
                <img
                  src={qrDataUrl}
                  alt="DPP QR code"
                  width={96}
                  height={96}
                  className="rounded-lg"
                  style={{ border: "1px solid #DCDCE0" }}
                />
                <button
                  onClick={downloadQr}
                  className="text-[11px] underline underline-offset-2"
                  style={{ color: "#6E6E73" }}
                >
                  Download QR
                </button>
              </div>
            )}

            <div className="flex flex-col gap-2">
              <button
                onClick={downloadJson}
                className="rounded-full px-5 py-2.5 text-[13px] font-semibold text-white transition-opacity hover:opacity-85"
                style={{ background: "#0B5FD0" }}
              >
                Download AAS JSON
              </button>
              <button
                onClick={() => navigator.clipboard.writeText(window.location.href)}
                className="rounded-full border px-5 py-2.5 text-[13px] font-medium transition-colors hover:opacity-80"
                style={{ border: "1px solid #DCDCE0", color: "#17181A" }}
              >
                Copy passport link
              </button>
            </div>

            <div className="ml-auto text-right">
              <p className="font-mono text-[10px]" style={{ color: "#6E6E73" }}>
                Generated {new Date(dpp!.generatedAt).toLocaleDateString()}
              </p>
              <p className="font-mono text-[10px]" style={{ color: "#6E6E73" }}>
                {elements.length} elements · IDTA 02006
              </p>
            </div>
          </div>
        </div>
      </div>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="min-h-screen px-6 py-12"
      style={{ background: "#F5F5F7", fontFamily: "Inter, system-ui, sans-serif" }}
    >
      {children}
    </div>
  );
}
