"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface GapField {
  name: string;
  hint: string;
  required: boolean;
}

interface Session {
  productName: string;
  productUrl: string;
  gaps: GapField[];
  responded: boolean;
  branding?: {
    orgName?: string;
    logoUrl?: string;
    brandColor?: string;
  };
}

export default function ReplyPage({ params }: { params: Promise<{ token: string }> & { token: string } }) {
  const [session, setSession] = useState<Session | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [phase, setPhase] = useState<"loading" | "form" | "done" | "error">(
    "loading"
  );
  const [errorMsg, setErrorMsg] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetch(`/api/session/${params.token}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.error) {
          setErrorMsg(
            data.error === "Session not found or expired."
              ? "This link has expired or is not valid. Please ask for a new data request."
              : data.error
          );
          setPhase("error");
        } else {
          setSession(data);
          setPhase(data.responded ? "done" : "form");
        }
      })
      .catch(() => {
        setErrorMsg("Could not load this request. Please try refreshing the page.");
        setPhase("error");
      });
  }, [params.token]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const res = await fetch(`/api/session/${params.token}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ response: values }),
      });
      if (res.ok) {
        setPhase("done");
      } else {
        const d = await res.json().catch(() => ({}));
        setErrorMsg(d.error ?? "Submission failed. Please try again.");
        setPhase("error");
      }
    } catch {
      setErrorMsg("Network error. Please check your connection and try again.");
      setPhase("error");
    } finally {
      setSubmitting(false);
    }
  }

  // ── Loading ───────────────────────────────────────────────────────────────
  if (phase === "loading") {
    return (
      <Shell>
        <div className="flex justify-center pt-24">
          <div className="flex gap-1.5">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="h-2 w-2 animate-pulse rounded-full"
                style={{
                  background: "#6E6E73",
                  animationDelay: `${i * 140}ms`,
                }}
              />
            ))}
          </div>
        </div>
      </Shell>
    );
  }

  // ── Error ─────────────────────────────────────────────────────────────────
  if (phase === "error") {
    return (
      <Shell>
        <Card>
          <div className="text-center">
            <div
              className="mx-auto mb-5 grid h-12 w-12 place-items-center rounded-full"
              style={{ background: "#FEF3E2" }}
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path
                  d="M10 6v5M10 14h.01"
                  stroke="#B8760B"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                />
                <circle cx="10" cy="10" r="8.5" stroke="#B8760B" strokeWidth="1.5" />
              </svg>
            </div>
            <p className="text-[16px] font-semibold" style={{ color: "#17181A" }}>
              Request not found
            </p>
            <p
              className="mt-2 text-[14px] leading-relaxed"
              style={{ color: "#6E6E73" }}
            >
              {errorMsg}
            </p>
          </div>
        </Card>
      </Shell>
    );
  }

  // ── Done ──────────────────────────────────────────────────────────────────
  if (phase === "done") {
    return (
      <Shell>
        <Card>
          <div className="text-center">
            <div
              className="mx-auto mb-5 grid h-12 w-12 place-items-center rounded-full"
              style={{ background: "#E6F5EE" }}
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path
                  d="M4 10.5l4 4 8-8"
                  stroke="#1B8A5A"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <p className="text-[17px] font-semibold" style={{ color: "#17181A" }}>
              Thank you!
            </p>
            <p
              className="mt-2 text-[14px] leading-relaxed"
              style={{ color: "#6E6E73" }}
            >
              Your data for{" "}
              <strong style={{ color: "#17181A" }}>{session?.productName}</strong>{" "}
              has been received. MIA will use it to complete the Digital Product
              Passport automatically.
            </p>
            <p className="mt-4 text-[13px]" style={{ color: "#6E6E73" }}>
              You can close this window.
            </p>
          </div>
        </Card>
      </Shell>
    );
  }

  // ── Form ──────────────────────────────────────────────────────────────────
  const requiredCount = session?.gaps.filter((g) => g.required).length ?? 0;

  return (
    <Shell>
      <div style={{ maxWidth: 520, margin: "0 auto" }}>
        {/* Brand header — custom if org has branding, else MIA default */}
        <div className="mb-8">
          {session?.branding?.logoUrl ? (
            <img
              src={session.branding.logoUrl}
              alt={session.branding.orgName ?? "Logo"}
              className="h-10 object-contain"
              onError={(e) => ((e.target as HTMLImageElement).style.display = "none")}
            />
          ) : (
            <div className="flex items-center gap-2">
              <span
                className="grid h-6 w-6 place-items-center rounded-md"
                style={{ background: "#17181A" }}
              >
                <span className="rounded-[1px]" style={{ height: 6, width: 6, background: "#FFFFFF" }} />
              </span>
              <span className="text-[15px] font-semibold tracking-tight" style={{ color: "#17181A" }}>
                {session?.branding?.orgName ?? "MIA"}
              </span>
            </div>
          )}
        </div>

        {/* Title */}
        <h1
          className="mb-2 text-[24px] font-semibold leading-tight tracking-tight"
          style={{ color: "#17181A" }}
        >
          Product data request
        </h1>
        <p className="mb-6 text-[15px] leading-relaxed" style={{ color: "#6E6E73" }}>
          Please provide the details below for{" "}
          <strong style={{ color: "#17181A" }}>{session?.productName}</strong>.
          {session?.productUrl && (
            <>
              {" "}
              <a
                href={session.productUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="underline underline-offset-2"
                style={{ color: "#0B5FD0" }}
              >
                View product page
              </a>
            </>
          )}{" "}
          This information is required for EU ESPR Digital Product Passport compliance.
          {requiredCount > 0 && (
            <span style={{ color: "#B8760B" }}>
              {" "}
              {requiredCount} field{requiredCount > 1 ? "s are" : " is"} mandatory.
            </span>
          )}
        </p>

        {/* Field form */}
        <form onSubmit={submit} className="space-y-4">
          {session?.gaps.map((gap) => (
            <div
              key={gap.name}
              className="rounded-2xl p-5"
              style={{ border: "1px solid #DCDCE0", background: "#FFFFFF" }}
            >
              <label className="block">
                <p
                  className="font-mono text-[13px] font-medium"
                  style={{ color: "#17181A" }}
                >
                  {gap.name}
                  {gap.required && (
                    <span
                      className="ml-2 rounded-full px-2 py-0.5 font-mono text-[10px]"
                      style={{ background: "#FEF3E2", color: "#B8760B" }}
                    >
                      required
                    </span>
                  )}
                </p>
                <p
                  className="mt-1 text-[13px] leading-relaxed"
                  style={{ color: "#6E6E73" }}
                >
                  {gap.hint}
                </p>
                <input
                  type="text"
                  required={gap.required}
                  value={values[gap.name] ?? ""}
                  onChange={(e) =>
                    setValues((prev) => ({ ...prev, [gap.name]: e.target.value }))
                  }
                  placeholder={`Enter ${gap.name}...`}
                  className="mt-3 w-full rounded-xl px-4 py-2.5 text-[14px] transition-colors focus:outline-none"
                  style={{
                    border: "1px solid #DCDCE0",
                    background: "#F5F5F7",
                    color: "#17181A",
                  }}
                  onFocus={(e) => {
                    e.target.style.borderColor = "#0B5FD0";
                    e.target.style.background = "#FFFFFF";
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = "#DCDCE0";
                    e.target.style.background = "#F5F5F7";
                  }}
                />
              </label>
            </div>
          ))}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-full py-3.5 text-[15px] font-semibold text-white transition-opacity hover:opacity-85 disabled:opacity-40"
            style={{ background: session?.branding?.brandColor ?? "#17181A" }}
          >
            {submitting ? "Submitting..." : "Submit product data"}
          </button>
        </form>

        <p
          className="mt-8 text-center text-[12px]"
          style={{ color: "#6E6E73" }}
        >
          Powered by{" "}
          <Link
            href="/"
            className="underline underline-offset-2 hover:opacity-75"
          >
            MIA
          </Link>{" "}
          &mdash; Digital Product Passport generator for EU ESPR compliance.
        </p>
      </div>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="min-h-screen px-6 py-16"
      style={{ background: "#F5F5F7", fontFamily: "Inter, system-ui, sans-serif" }}
    >
      {children}
    </div>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="mx-auto max-w-md rounded-2xl p-10"
      style={{ background: "#FFFFFF", border: "1px solid #DCDCE0" }}
    >
      {children}
    </div>
  );
}
