"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";

interface ShellData {
  id: string;
  idShort?: string;
  assetInformation?: {
    globalAssetId?: string;
  };
}

function decodeBase64Url(encoded: string): string {
  // Add padding back
  const padded = encoded + "=".repeat((4 - (encoded.length % 4)) % 4);
  return atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
}

export default function PassportPage() {
  const params = useParams();
  const searchParams = useSearchParams();

  const encodedId = typeof params.id === "string" ? params.id : Array.isArray(params.id) ? params.id[0] : "";

  const [shellId, setShellId] = useState<string>("");
  const [shellData, setShellData] = useState<ShellData | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // QR may be passed as query param if navigating directly from the workspace
  const qrFromQuery = searchParams.get("qr");
  const basyxUrl = searchParams.get("basyx") ?? "https://v3.admin-shell.io";

  useEffect(() => {
    if (!encodedId) return;
    let decoded: string;
    try {
      decoded = decodeBase64Url(encodedId);
      setShellId(decoded);
    } catch {
      setLoadError("Invalid passport identifier.");
      setLoading(false);
      return;
    }

    // Try to fetch shell data from BaSyx directly
    const fetchShell = async () => {
      try {
        const shellUrl = `${basyxUrl}/shells/${encodedId}`;
        const res = await fetch(shellUrl, {
          headers: { Accept: "application/json" },
        });
        if (res.ok) {
          const data = (await res.json()) as ShellData;
          setShellData(data);
        }
      } catch {
        // BaSyx may not be reachable — we still show the passport page with the ID
      } finally {
        setLoading(false);
      }
    };

    void fetchShell();
  }, [encodedId, basyxUrl]);

  const productName =
    shellData?.idShort ??
    shellData?.assetInformation?.globalAssetId?.split("/").pop() ??
    (shellId ? shellId.split(":").pop() ?? "Product" : "Product");

  const basyxShellUrl = `${basyxUrl}/shells/${encodedId}`;

  return (
    <div className="min-h-screen bg-white" style={{ fontFamily: "system-ui, sans-serif" }}>
      {/* Header */}
      <header className="border-b border-[#e8e8e8] bg-white px-6 py-4">
        <div className="mx-auto flex max-w-2xl items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className="grid h-8 w-8 place-items-center rounded-lg"
              style={{ background: "linear-gradient(135deg, #3b5bdb 0%, #4dabf7 100%)" }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                <path
                  d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                  stroke="white"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <span className="text-[15px] font-semibold text-[#1a1a1a]">MIA</span>
          </div>
          <span className="rounded-full border border-[#e8e8e8] px-3 py-1 text-[11px] font-medium uppercase tracking-wider text-[#666]">
            Digital Product Passport
          </span>
        </div>
      </header>

      {/* Main content */}
      <main className="mx-auto max-w-2xl px-6 py-12">
        {loading ? (
          <div className="flex flex-col items-center py-24">
            <div
              className="h-8 w-8 animate-spin rounded-full border-2 border-[#e8e8e8]"
              style={{ borderTopColor: "#3b5bdb" }}
            />
            <p className="mt-4 text-[14px] text-[#888]">Loading passport...</p>
          </div>
        ) : loadError ? (
          <div className="rounded-2xl border border-red-100 bg-red-50 p-8 text-center">
            <p className="text-[15px] font-semibold text-red-700">Invalid passport</p>
            <p className="mt-1 text-[13px] text-red-500">{loadError}</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-8">
            {/* Product name */}
            <div className="text-center">
              <h1 className="text-[28px] font-bold tracking-tight text-[#1a1a1a]">
                {productName}
              </h1>
              <p className="mt-1 text-[14px] text-[#888]">
                EU ESPR Digital Product Passport
              </p>
            </div>

            {/* QR code section */}
            <div className="flex flex-col items-center gap-4 rounded-2xl border border-[#e8e8e8] bg-[#fafafa] p-8 shadow-sm">
              {qrFromQuery ? (
                <img
                  src={`data:image/png;base64,${qrFromQuery}`}
                  alt="Passport QR Code"
                  className="h-56 w-56"
                  style={{ imageRendering: "pixelated" }}
                />
              ) : (
                <div className="flex h-56 w-56 flex-col items-center justify-center rounded-xl border border-dashed border-[#d0d0d0] bg-white text-[#aaa]">
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <rect x="3" y="3" width="7" height="7" />
                    <rect x="14" y="3" width="7" height="7" />
                    <rect x="3" y="14" width="7" height="7" />
                    <path d="M14 14h.01M18 14h.01M14 18h.01M18 18h.01M14 22h.01M18 22h.01M22 14h.01M22 18h.01M22 22h.01" strokeLinecap="round" />
                  </svg>
                  <p className="mt-2 text-[11px]">QR not available</p>
                </div>
              )}
              <p className="text-[13px] font-medium text-[#555]">Scan to verify this passport</p>
            </div>

            {/* Passport ID & live data link */}
            <div className="w-full rounded-2xl border border-[#e8e8e8] bg-white p-6 shadow-sm">
              <div className="space-y-4">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-[#aaa]">
                    Passport ID
                  </p>
                  <p className="mt-1 break-all font-mono text-[12px] text-[#333]">{shellId}</p>
                </div>
                <div className="border-t border-[#f0f0f0]" />
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-[#aaa]">
                    Live AAS Data
                  </p>
                  <a
                    href={basyxShellUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 block break-all font-mono text-[12px] text-[#3b5bdb] underline underline-offset-2"
                  >
                    {basyxShellUrl}
                  </a>
                </div>
                <div className="border-t border-[#f0f0f0]" />
                <div className="flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full bg-green-500" />
                  <p className="text-[12px] text-[#555]">
                    Deployed to IDTA public AAS repository
                  </p>
                </div>
              </div>
            </div>

            {/* Standards badges */}
            <div className="flex flex-wrap justify-center gap-2">
              {["IDTA 02006", "AAS v3.0", "EU ESPR"].map((badge) => (
                <span
                  key={badge}
                  className="rounded-full border border-[#e0e8ff] bg-[#f0f4ff] px-3 py-1 text-[11px] font-medium text-[#3b5bdb]"
                >
                  {badge}
                </span>
              ))}
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-[#e8e8e8] px-6 py-6 text-center">
        <p className="text-[12px] text-[#aaa]">
          Powered by{" "}
          <a
            href="https://mia-dpp.vercel.app"
            className="font-medium text-[#3b5bdb]"
            target="_blank"
            rel="noopener noreferrer"
          >
            MIA
          </a>{" "}
          -- Mittelstand Integration Agent
        </p>
      </footer>
    </div>
  );
}
