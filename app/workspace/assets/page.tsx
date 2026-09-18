"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface Passport {
  id: string;
  thread_id: string;
  product_name: string;
  submodel: string;
  status: "draft" | "deployed";
  qr_code_b64: string | null;
  passport_url: string | null;
  basyx_shell_id: string | null;
  created_at: string;
  updated_at: string;
}

export default function AssetsPage() {
  const [passports, setPassports] = useState<Passport[]>([]);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/passports")
      .then((r) => r.json())
      .then((data) => {
        setPassports(Array.isArray(data) ? data : []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  function copyLink(url: string, id: string) {
    navigator.clipboard.writeText(url);
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  }

  return (
    <div className="px-8 py-8">
      <div className="mx-auto max-w-shell">
        {/* Header */}
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-[22px] font-semibold tracking-tight text-ink">My Assets</h1>
            {!loading && passports.length > 0 && (
              <p className="mt-1 text-[13px] text-muted">
                {passports.length} passport{passports.length !== 1 ? "s" : ""}
              </p>
            )}
          </div>
          <Link
            href="/workspace"
            className="flex items-center gap-2 rounded-full bg-ink px-4 py-2 text-[13px] font-medium text-white transition-all hover:-translate-y-px hover:shadow-md"
          >
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
              <path d="M6.5 1v11M1 6.5h11" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
            New passport
          </Link>
        </div>

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
        {!loading && passports.length === 0 && (
          <div className="flex min-h-[400px] items-center justify-center rounded-2xl border border-hairline bg-paper">
            <div className="max-w-xs px-8 py-12 text-center">
              <div className="mx-auto mb-5 grid h-14 w-14 place-items-center rounded-2xl border border-hairline bg-mist text-muted">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                </svg>
              </div>
              <p className="text-[16px] font-semibold text-ink">No passports yet</p>
              <p className="mt-2 text-[13px] leading-relaxed text-muted">
                Start a new chat to create your first Digital Product Passport.
              </p>
              <Link
                href="/workspace"
                className="mt-5 inline-flex items-center gap-2 rounded-full bg-ink px-5 py-2.5 text-[13px] font-medium text-white transition-all hover:-translate-y-px hover:shadow-md"
              >
                Start now
              </Link>
            </div>
          </div>
        )}

        {/* Passport grid */}
        {!loading && passports.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {passports.map((p) => (
              <PassportCard
                key={p.id}
                passport={p}
                copied={copied === p.id}
                onCopy={() => p.passport_url && copyLink(p.passport_url, p.id)}
              />
            ))}

            {/* New passport card */}
            <Link
              href="/workspace"
              className="flex min-h-[280px] flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-hairline text-muted transition-colors hover:border-signal/40 hover:text-signal"
            >
              <div className="grid h-10 w-10 place-items-center rounded-xl border border-current">
                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                  <path d="M9 2v14M2 9h14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                </svg>
              </div>
              <span className="text-[13px] font-medium">New passport</span>
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}

function PassportCard({
  passport,
  copied,
  onCopy,
}: {
  passport: Passport;
  copied: boolean;
  onCopy: () => void;
}) {
  const deployed = passport.status === "deployed" && passport.qr_code_b64;
  const date = new Date(passport.updated_at).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });

  return (
    <div className="flex flex-col overflow-hidden rounded-2xl border border-hairline bg-paper transition-shadow hover:shadow-sm">
      {/* QR or placeholder */}
      <div className="flex h-44 items-center justify-center border-b border-hairline bg-mist">
        {deployed ? (
          <img
            src={`data:image/png;base64,${passport.qr_code_b64}`}
            alt={`QR code for ${passport.product_name}`}
            className="h-36 w-36 rounded-lg"
          />
        ) : (
          <div className="flex flex-col items-center gap-2 text-muted">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="7" height="7" rx="1" />
              <rect x="14" y="3" width="7" height="7" rx="1" />
              <rect x="3" y="14" width="7" height="7" rx="1" />
              <path d="M14 14h.01M18 14h.01M14 18h.01M18 18h.01M14 21h4" />
            </svg>
            <span className="text-[11px]">Not deployed yet</span>
          </div>
        )}
      </div>

      {/* Info */}
      <div className="flex flex-1 flex-col p-4">
        <p className="truncate text-[14px] font-semibold text-ink">{passport.product_name}</p>
        <p className="mt-0.5 font-mono text-[11px] text-muted">{passport.submodel}</p>

        <div className="mt-2 flex items-center gap-1.5">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              deployed ? "bg-ok" : "bg-warn"
            }`}
          />
          <span className={`text-[12px] font-medium ${deployed ? "text-ok" : "text-warn"}`}>
            {deployed ? "Deployed" : "Draft"}
          </span>
          <span className="ml-auto text-[11px] text-muted">{date}</span>
        </div>

        {/* Actions */}
        <div className="mt-4 flex gap-2">
          {deployed && passport.passport_url ? (
            <>
              <a
                href={passport.passport_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex-1 rounded-lg border border-hairline py-1.5 text-center text-[12px] font-medium text-ink transition-colors hover:bg-mist"
              >
                Open
              </a>
              <button
                onClick={onCopy}
                className="flex-1 rounded-lg border border-hairline py-1.5 text-center text-[12px] font-medium text-ink transition-colors hover:bg-mist"
              >
                {copied ? "Copied!" : "Share"}
              </button>
            </>
          ) : (
            <Link
              href={`/workspace?thread=${passport.thread_id}`}
              className="flex-1 rounded-lg border border-hairline py-1.5 text-center text-[12px] font-medium text-ink transition-colors hover:bg-mist"
            >
              Continue
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
