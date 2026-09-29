"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useUser } from "@clerk/nextjs";
import type {
  AgentResponse,
  AgentTraceEvent,
  ChatMessage,
  ExtractedField,
} from "@/lib/types";
import { ChatMarkdown } from "@/components/ChatMarkdown";
import { OnboardingModal, getCompanyProfile } from "@/components/OnboardingModal";

const API_URL = process.env.NEXT_PUBLIC_MIA_API_URL ?? "";


function getGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export default function Workspace() {
  const { user } = useUser();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [agentStatus, setAgentStatus] = useState<AgentResponse["status"]>("completed");
  const [extractedFields, setExtractedFields] = useState<Record<string, string>>({});
  const [missingRequired, setMissingRequired] = useState<string[]>([]);
  const [dppReady, setDppReady] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  // ── Deploy state ──────────────────────────────────────────────────────────
  const [deployStatus, setDeployStatus] = useState<"idle" | "deploying" | "deployed" | "error">("idle");
  const [deployResult, setDeployResult] = useState<{
    passport_url: string;
    qr_code_png_b64: string;
    shell_ids: string[];
  } | null>(null);
  const [deployError, setDeployError] = useState("");

  // ── File upload state ─────────────────────────────────────────────────────
  const [uploadStatus, setUploadStatus] = useState<"idle" | "uploading" | "error">("idle");
  const [uploadError, setUploadError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Product image state ───────────────────────────────────────────────────
  const [productImageUrl, setProductImageUrl] = useState<string | null>(null);
  const [imageSource, setImageSource] = useState<"og" | "upload" | null>(null);
  const [imageSearchedUrl, setImageSearchedUrl] = useState<string | null>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);

  // ── Onboarding ────────────────────────────────────────────────────────────
  const [showOnboarding, setShowOnboarding] = useState(false);
  useEffect(() => {
    if (typeof window !== "undefined") {
      const onboarded = localStorage.getItem("mia.onboarded.v1");
      if (!onboarded) setShowOnboarding(true);
    }
  }, []);

  // ── Supplier outreach state ───────────────────────────────────────────────
  const [supplierEmail, setSupplierEmail] = useState("");
  const [outreachStatus, setOutreachStatus] = useState<
    "idle" | "sending" | "sent" | "responded" | "error"
  >("idle");
  const [outreachToken, setOutreachToken] = useState<string | null>(null);
  const [outreachError, setOutreachError] = useState("");
  const outreachPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Poll for supplier response every 10s after email is sent
  useEffect(() => {
    if (outreachStatus !== "sent" || !outreachToken) return;
    outreachPollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/session/${outreachToken}`);
        if (res.ok) {
          const data = (await res.json()) as { responded?: boolean; response?: Record<string, string> };
          if (data.responded && data.response) {
            setOutreachStatus("responded");
            clearInterval(outreachPollRef.current!);
            const filled = Object.entries(data.response)
              .map(([k, v]) => `${k}: ${v}`)
              .join(", ");
            void send(`Supplier provided missing data -- ${filled}`);
          }
        }
      } catch { /* ignore poll errors */ }
    }, 10_000);
    return () => clearInterval(outreachPollRef.current!);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [outreachStatus, outreachToken]);

  async function sendGapEmail() {
    if (!supplierEmail || missingRequired.length === 0) return;
    const profile = getCompanyProfile();
    setOutreachStatus("sending");
    setOutreachError("");
    try {
      const res = await fetch("/api/email/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contactEmail: supplierEmail,
          productName: extractedFields["ManufacturerProductDesignation"] || profile?.name || "Product",
          productUrl: "",
          gaps: missingRequired,
        }),
      });
      const data = (await res.json()) as { token?: string; sent?: boolean; error?: string };
      if (res.ok) {
        setOutreachToken(data.token ?? null);
        setOutreachStatus("sent");
      } else {
        setOutreachError(data.error ?? "Failed to send email.");
        setOutreachStatus("error");
      }
    } catch {
      setOutreachError("Network error. Please try again.");
      setOutreachStatus("error");
    }
  }

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  function activeThread(): string {
    const active = threadId ?? `thread-${crypto.randomUUID()}`;
    if (!threadId) setThreadId(active);
    return active;
  }

  function applyAgentResponse(data: AgentResponse) {
    setThreadId(data.threadId);
    setAgentStatus(data.status);
    setMissingRequired(data.missingRequired);
    setDppReady(data.dppReady);
    if (data.extractedFields.length > 0) {
      setExtractedFields((prev) => {
        const next = { ...prev };
        for (const f of data.extractedFields) {
          next[f.idtaField] = f.value;
        }
        // Auto-fetch OG image when URIOfTheProduct first appears
        const uri = next["URIOfTheProduct"];
        if (uri && !prev["URIOfTheProduct"]) {
          void fetchOgImage(uri);
        }
        return next;
      });
    }
  }

  async function fetchOgImage(url: string) {
    if (imageSearchedUrl === url) return; // already tried
    setImageSearchedUrl(url);
    try {
      const res = await fetch(`/api/fetch-og-image?url=${encodeURIComponent(url)}`);
      const data = (await res.json()) as { imageUrl: string | null };
      if (data.imageUrl) {
        setProductImageUrl(data.imageUrl);
        setImageSource("og");
        // Add a chat message so the user sees it naturally
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant" as const,
            content: `I found a product image from the website. If you'd like a different image, use the upload button below.`,
          },
        ]);
      }
    } catch { /* silent — image is optional */ }
  }

  async function uploadProductImage(file: File) {
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch("/api/upload-image", { method: "POST", body: form });
      const data = (await res.json()) as { url?: string; error?: string };
      if (data.url) {
        setProductImageUrl(data.url);
        setImageSource("upload");
        setMessages((prev) => [
          ...prev,
          { role: "assistant" as const, content: "Product image uploaded successfully." },
        ]);
      }
    } catch { /* non-blocking */ }
  }

  async function callAgent(payload: Record<string, unknown>): Promise<AgentResponse> {
    const res = await fetch(`${API_URL}/api/agent/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = (await res.json()) as AgentResponse | { detail?: string };
    if (!res.ok) {
      throw new Error("detail" in body && body.detail ? body.detail : `Backend returned ${res.status}`);
    }
    return body as AgentResponse;
  }

  async function send(text: string) {
    const t = text.trim();
    if (!t || busy) return;

    const profile = getCompanyProfile();
    const next: ChatMessage[] = [...messages, { role: "user", content: t }];
    setMessages(next);
    setInput("");
    const tid = activeThread();
    setBusy(true);

    try {
      const data = await callAgent({
        threadId: tid,
        message: t,
        companyName: profile?.name || undefined,
        companyWebsite: profile?.website || undefined,
      });
      applyAgentResponse(data);
      setMessages((prev) => [...prev, { role: "assistant", content: data.reply }]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "That request didn't go through. Check your connection and send it again." },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function ingestWebsite() {
    const url = input.trim();
    if (!url || busy) return;
    // In the document-first flow, we just send the URL as a chat message
    // The agent will note it as context even though it cannot scrape it
    void send(`Product URL for reference: ${url}`);
  }

  async function uploadFile(file: File) {
    if (busy) return;
    setUploadStatus("uploading");
    setUploadError("");
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch("/api/upload", { method: "POST", body: form });
      const data = (await res.json()) as {
        text?: string;
        fileName?: string;
        fileType?: string;
        sizeKb?: number;
        truncated?: boolean;
        error?: string;
      };
      if (!res.ok || data.error) {
        throw new Error(data.error ?? `Upload failed (${res.status})`);
      }
      setUploadStatus("idle");

      const displayText = `${data.fileName} (${data.fileType}, ${data.sizeKb} KB)${data.truncated ? " — large file, first 40 000 chars extracted" : ""}`;
      const profile = getCompanyProfile();
      const tid = activeThread();
      setBusy(true);
      setMessages((prev) => [...prev, { role: "user", content: displayText }]);

      try {
        const agentData = await callAgent({
          threadId: tid,
          message: "Extract all IDTA 02006 Digital Nameplate fields from this document.",
          documentText: data.text,
          documentFilename: data.fileName,
          documentType: data.fileType,
          companyName: profile?.name || undefined,
          companyWebsite: profile?.website || undefined,
        });
        applyAgentResponse(agentData);
        setMessages((prev) => [...prev, { role: "assistant", content: agentData.reply }]);
      } catch (agentErr) {
        const msg = agentErr instanceof Error ? agentErr.message : "unknown error";
        setMessages((prev) => [...prev, { role: "assistant", content: `Could not process the file: ${msg}` }]);
      } finally {
        setBusy(false);
      }
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
      setUploadStatus("error");
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) void uploadFile(file);
    e.target.value = "";
  }

  async function generate() {
    if (!dppReady && Object.keys(extractedFields).length === 0) return;
    const profile = getCompanyProfile();
    const productName =
      extractedFields["ManufacturerProductDesignation"] ||
      extractedFields["ManufacturerArticleNumber"] ||
      profile?.name ||
      "Product";
    setBusy(true);
    try {
      const tid = threadId ?? `thread-${crypto.randomUUID()}`;
      const res = await fetch(`${API_URL}/api/agent/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          productName,
          fields: extractedFields,
          threadId: tid,
        }),
      });
      const body = (await res.json()) as { threadId?: string; detail?: string; [key: string]: unknown };
      if (!res.ok) {
        throw new Error(body.detail ?? `Backend returned ${res.status}`);
      }
      // DPP generated — now deploy to BaSyx
      if (!threadId) setThreadId(tid);
      void deployPassport(tid);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "unknown error";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Could not generate the passport: ${msg}` },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function deployPassport(tid?: string) {
    const deployThreadId = tid ?? threadId;
    if (!deployThreadId || deployStatus === "deploying") return;
    setDeployStatus("deploying");
    setDeployError("");
    try {
      const res = await fetch(`${API_URL}/api/workspaces/${deployThreadId}/deploy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          basyx_url: "https://v3.admin-shell.io",
          passport_base_url: process.env.NEXT_PUBLIC_BASE_URL ?? "https://mia-dpp.vercel.app",
        }),
      });
      const body = (await res.json()) as {
        passport_url?: string;
        qr_code_png_b64?: string;
        shell_ids?: string[];
        aas_json?: Record<string, unknown>;
        detail?: string;
      };
      if (!res.ok) {
        throw new Error(body.detail ?? `Deploy failed: ${res.status}`);
      }
      const result = {
        passport_url: body.passport_url ?? "",
        qr_code_png_b64: body.qr_code_png_b64 ?? "",
        shell_ids: body.shell_ids ?? [],
      };
      setDeployResult(result);
      setDeployStatus("deployed");
      // Save to Supabase registry including the AAS JSON for self-hosted passport page
      void savePassportRecord({
        status: "deployed",
        qr_code_b64: result.qr_code_png_b64,
        passport_url: result.passport_url,
        basyx_shell_id: result.shell_ids[0] ?? null,
        aas_json: body.aas_json ?? null,
      });
    } catch (error) {
      setDeployError(error instanceof Error ? error.message : "Deployment failed.");
      setDeployStatus("error");
    }
  }

  async function savePassportRecord(overrides: {
    status?: "draft" | "deployed";
    qr_code_b64?: string;
    passport_url?: string;
    basyx_shell_id?: string | null;
    aas_json?: Record<string, unknown> | null;
  } = {}) {
    const tid = threadId;
    const profile = getCompanyProfile();
    const pname = extractedFields["ManufacturerProductDesignation"] || profile?.name || "Product";
    if (!tid) return;
    try {
      await fetch("/api/passports", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          thread_id: tid,
          product_name: pname,
          submodel: "IDTA 02006",
          product_image_url: productImageUrl,
          ...overrides,
        }),
      });
    } catch { /* non-blocking */ }
  }

  const productName = extractedFields["ManufacturerProductDesignation"] ||
    extractedFields["ManufacturerArticleNumber"] || "";
  const hasChat = messages.length > 0;
  const hasExtracted = Object.keys(extractedFields).length > 0;
  const firstName = user?.firstName ?? user?.username ?? "";

  return (
    <>
      {showOnboarding && (
        <OnboardingModal onClose={() => setShowOnboarding(false)} />
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.xlsx,.xls,.csv,.docx,.txt"
        className="hidden"
        onChange={handleFileChange}
      />
      <input
        ref={imageInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void uploadProductImage(file);
          e.target.value = "";
        }}
      />

      <div className="flex h-full flex-col">
        {/* Top bar */}
        {hasChat && (
          <header className="shrink-0 flex h-14 items-center justify-between border-b border-hairline bg-paper px-6">
            <span className="text-[14px] font-medium text-ink truncate">
              {productName || "New passport"}
            </span>
            <div className="flex items-center gap-3">
              {threadId && (
                <a
                  href={`/workspace/activity?thread=${threadId}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[12px] text-muted hover:text-ink transition-colors"
                >
                  Agent activity →
                </a>
              )}
              {dppReady && deployStatus === "idle" && (
                <button
                  onClick={() => void generate()}
                  disabled={busy}
                  className="rounded-full bg-ink px-4 py-1.5 text-[13px] font-medium text-white transition-all hover:shadow-md hover:-translate-y-px disabled:opacity-40"
                >
                  Generate passport
                </button>
              )}
            </div>
          </header>
        )}

        <div className="flex min-h-0 flex-1">
          <section className="flex min-h-0 flex-1 flex-col">
            <div className="scroll-quiet flex-1 overflow-y-auto">
              {!hasChat ? (
                /* ── Empty / hero state ── */
                <div className="flex min-h-full flex-col items-center justify-center px-6 py-16 animate-rise">
                  <div className="w-full max-w-xl">
                    <h1 className="text-[28px] font-semibold tracking-tight text-ink">
                      {getGreeting()}{firstName ? `, ${firstName}` : ""}.
                    </h1>
                    <p className="mt-1.5 text-[15px] text-muted">
                      What would you like to work on?
                    </p>

                    <div className="mt-6">
                      <div className="flex items-end gap-2 rounded-[20px] border border-hairline bg-paper p-1.5 shadow-sm transition-all focus-within:border-signal/40 focus-within:ring-4 focus-within:ring-signal/10">
                        <textarea
                          value={input}
                          onChange={(e) => setInput(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && !e.shiftKey) {
                              e.preventDefault();
                              void send(input);
                            }
                          }}
                          rows={2}
                          placeholder="Describe a product or paste specs..."
                          className="max-h-40 flex-1 resize-none bg-transparent px-4 py-2.5 text-[14px] leading-relaxed text-ink placeholder:text-muted focus:outline-none"
                        />
                        <button
                          onClick={() => void send(input)}
                          disabled={busy || !input.trim()}
                          className="mb-0.5 mr-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-full bg-ink text-white transition-transform hover:scale-105 disabled:scale-100 disabled:opacity-25"
                          aria-label="Send message"
                        >
                          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                            <path d="M8 13V3M8 3L3.5 7.5M8 3l4.5 4.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        </button>
                      </div>
                    </div>

                    <div className="mt-3 flex items-center gap-2">
                      <button
                        onClick={() => fileInputRef.current?.click()}
                        disabled={busy || uploadStatus === "uploading"}
                        className="flex items-center gap-1.5 rounded-full border border-hairline bg-paper px-3.5 py-2 text-[13px] font-medium text-muted transition-colors hover:border-signal/30 hover:text-signal disabled:opacity-40"
                      >
                        <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                          <path d="M8 11V2M8 2L4.5 5.5M8 2l3.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
                          <path d="M2 13h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                        </svg>
                        {uploadStatus === "uploading" ? "Reading file…" : "Add data source"}
                      </button>
                      <span className="text-[12px] text-muted">PDF, Excel, CSV, DOCX</span>
                      {uploadError && (
                        <span className="text-[12px] text-red-500">{uploadError}</span>
                      )}
                    </div>

                    <div className="mt-8">
                      <div className="flex items-center gap-3 mb-3">
                        <span className="text-[12px] font-semibold uppercase tracking-wider text-muted">
                          Recent assets
                        </span>
                        <span className="flex-1 border-t border-hairline" />
                      </div>
                      <div className="rounded-xl border border-hairline bg-paper p-6 text-center">
                        <p className="text-[14px] font-medium text-ink">No passports yet</p>
                        <p className="mt-1 text-[13px] text-muted">
                          Start a new chat to create your first Digital Product Passport.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                /* ── Active chat ── */
                <div className="px-6 py-6">
                  <div className="mx-auto max-w-2xl space-y-5">
                    {messages.map((m, i) => (
                      <div
                        key={i}
                        className={m.role === "user" ? "flex justify-end" : "flex justify-start"}
                      >
                        <div
                          className={
                            m.role === "user"
                              ? "max-w-[85%] rounded-2xl rounded-br-sm bg-gradient-to-tr from-signal to-blue-500 px-4 py-3 text-[14px] leading-relaxed text-white shadow-sm"
                              : "max-w-[92%] rounded-2xl rounded-bl-sm border border-hairline bg-paper px-4 py-3 text-[14px] leading-relaxed text-ink shadow-sm"
                          }
                        >
                          {m.role === "assistant" ? (
                            <ChatMarkdown>{m.content}</ChatMarkdown>
                          ) : (
                            m.content
                          )}
                        </div>
                      </div>
                    ))}

                    {/* ── Missing required fields card ─────────────── */}
                    {missingRequired.length > 0 && !busy && (
                      <div className="rounded-xl border border-warn/20 bg-warn/[0.04] p-4 space-y-3">
                        <div>
                          <p className="text-[13px] font-semibold text-warn">Missing required fields</p>
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            {missingRequired.map((g) => (
                              <span key={g} className="rounded-full border border-warn/20 bg-paper px-2.5 py-0.5 font-mono text-[11px] text-ink">
                                {g}
                              </span>
                            ))}
                          </div>
                          <p className="mt-2 text-[12px] text-muted">
                            Type the missing values in the chat, or send a data request to your supplier below.
                          </p>
                        </div>
                        {outreachStatus === "idle" || outreachStatus === "error" ? (
                          <div className="flex gap-2">
                            <input
                              type="email"
                              value={supplierEmail}
                              onChange={(e) => setSupplierEmail(e.target.value)}
                              placeholder="supplier@example.com"
                              className="flex-1 rounded-lg border border-hairline bg-paper px-3 py-2 text-[13px] text-ink placeholder:text-muted/60 focus:border-signal/50 focus:outline-none"
                            />
                            <button
                              onClick={() => void sendGapEmail()}
                              disabled={!supplierEmail || missingRequired.length === 0}
                              className="rounded-full bg-ink px-4 py-2 text-[12px] font-medium text-white disabled:opacity-30"
                            >
                              Send email
                            </button>
                          </div>
                        ) : outreachStatus === "sending" ? (
                          <p className="text-[12px] text-muted">Sending...</p>
                        ) : outreachStatus === "sent" ? (
                          <div className="flex items-center gap-2">
                            <span className="h-2 w-2 animate-pulse rounded-full bg-ok" />
                            <p className="text-[12px] text-muted">Email sent to <strong className="text-ink">{supplierEmail}</strong>. Auto-filling when they respond...</p>
                          </div>
                        ) : outreachStatus === "responded" ? (
                          <p className="text-[12px] font-medium text-ok">Supplier responded — fields auto-filled.</p>
                        ) : null}
                        {outreachStatus === "error" && <p className="text-[11px] text-warn">{outreachError}</p>}
                      </div>
                    )}

                    {/* ── Product image card ───────────────────────────── */}
                    {(productImageUrl || (Object.keys(extractedFields).length > 0 && !busy)) && (
                      <div className="rounded-xl border border-hairline bg-paper p-4">
                        <p className="text-[12px] font-semibold text-ink mb-3">Product image</p>
                        {productImageUrl ? (
                          <div className="flex items-start gap-4">
                            <img
                              src={productImageUrl}
                              alt="Product"
                              className="h-24 w-24 rounded-lg object-contain border border-hairline bg-mist"
                              onError={(e) => ((e.target as HTMLImageElement).style.display = "none")}
                            />
                            <div className="flex flex-col gap-2">
                              <p className="text-[12px] text-muted">
                                {imageSource === "og"
                                  ? "Extracted from product page"
                                  : "Uploaded by you"}
                              </p>
                              <button
                                onClick={() => imageInputRef.current?.click()}
                                className="text-[12px] font-medium text-signal hover:underline text-left"
                              >
                                Use a different image →
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div className="flex items-center gap-3">
                            <p className="text-[12px] text-muted flex-1">No product image yet.</p>
                            <button
                              onClick={() => imageInputRef.current?.click()}
                              className="rounded-full border border-hairline px-3 py-1.5 text-[12px] font-medium text-ink hover:bg-mist transition-colors"
                            >
                              Upload image
                            </button>
                          </div>
                        )}
                      </div>
                    )}

                    {/* ── DPP ready — Generate button ────────────────── */}
                    {dppReady && deployStatus === "idle" && !busy && (
                      <div className="rounded-xl border border-ok/20 bg-ok/[0.04] p-4">
                        <p className="text-[13px] font-semibold text-ok">All required fields found</p>
                        <p className="mt-1 text-[12px] text-muted">
                          MIA has all the data needed to generate your Digital Product Passport.
                        </p>
                        <button
                          onClick={() => void generate()}
                          className="mt-3 rounded-full bg-ink px-5 py-2 text-[13px] font-medium text-white transition-all hover:shadow-md hover:-translate-y-px"
                        >
                          Generate passport →
                        </button>
                      </div>
                    )}

                    {/* ── Deploying indicator ───────────────────────── */}
                    {deployStatus === "deploying" && (
                      <div className="rounded-xl border border-hairline bg-paper p-4">
                        <div className="flex items-center gap-3">
                          <div className="flex gap-1">
                            {[0, 1, 2].map((i) => (
                              <span key={i} className="h-2 w-2 animate-pulse rounded-full bg-muted" style={{ animationDelay: `${i * 150}ms` }} />
                            ))}
                          </div>
                          <span className="text-[13px] text-muted">Generating and deploying passport…</span>
                        </div>
                      </div>
                    )}

                    {/* ── DPP deployed — QR + live link ─────────────── */}
                    {deployStatus === "deployed" && deployResult && (
                      <div className="rounded-xl border border-ok/20 bg-ok/[0.04] p-4">
                        <div className="flex items-center gap-2 mb-4">
                          <span className="h-2 w-2 rounded-full bg-ok" />
                          <p className="text-[13px] font-semibold text-ink">Passport ready</p>
                        </div>
                        <div className="flex gap-4 items-start">
                          {deployResult.qr_code_png_b64 && (
                            <img
                              src={`data:image/png;base64,${deployResult.qr_code_png_b64}`}
                              alt="Passport QR Code"
                              className="h-32 w-32 rounded-lg border border-hairline"
                              style={{ imageRendering: "pixelated" }}
                            />
                          )}
                          <div className="flex-1 min-w-0">
                            <p className="text-[12px] text-muted mb-2">Shareable link:</p>
                            <p className="break-all font-mono text-[11px] text-ink bg-mist rounded-lg p-2">{deployResult.passport_url}</p>
                            <div className="mt-3 flex flex-wrap gap-2">
                              <button
                                onClick={() => void navigator.clipboard.writeText(deployResult!.passport_url)}
                                className="rounded-full border border-hairline bg-paper px-3 py-1.5 text-[12px] font-medium text-ink hover:bg-mist"
                              >
                                Copy link
                              </button>
                              <a
                                href={deployResult.passport_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="rounded-full border border-signal/30 bg-signalDim px-3 py-1.5 text-[12px] font-medium text-signal hover:bg-signal/15"
                              >
                                Open passport
                              </a>
                              <a
                                href="/workspace/assets"
                                className="rounded-full border border-hairline px-3 py-1.5 text-[12px] font-medium text-muted hover:text-ink"
                              >
                                View in Assets →
                              </a>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* ── Deploy error ──────────────────────────────── */}
                    {deployStatus === "error" && (
                      <div className="rounded-xl border border-warn/20 bg-warn/[0.04] p-4">
                        <p className="text-[13px] font-semibold text-warn">Deployment error</p>
                        <p className="mt-1 text-[12px] text-muted">{deployError}</p>
                        <button
                          onClick={() => { setDeployStatus("idle"); setDeployError(""); }}
                          className="mt-2 text-[12px] text-signal underline"
                        >
                          Try again
                        </button>
                      </div>
                    )}

                    {/* ── Extracted fields preview ──────────────────── */}
                    {hasExtracted && !busy && deployStatus === "idle" && (
                      <div className="rounded-xl border border-hairline bg-mist p-4">
                        <p className="text-[12px] font-semibold uppercase tracking-wider text-muted mb-3">
                          Extracted fields ({Object.keys(extractedFields).length})
                        </p>
                        <div className="space-y-1.5">
                          {Object.entries(extractedFields).map(([field, value]) => (
                            <div key={field} className="flex gap-2">
                              <span className="shrink-0 font-mono text-[11px] text-muted w-48">{field}</span>
                              <span className="text-[12px] text-ink">{value}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {busy && (
                      <div className="flex items-center gap-3 py-2">
                        <div className="flex gap-1">
                          {[0, 1, 2].map((i) => (
                            <span
                              key={i}
                              className="h-2 w-2 animate-pulse rounded-full bg-muted"
                              style={{ animationDelay: `${i * 150}ms` }}
                            />
                          ))}
                        </div>
                        <span className="text-[13px] text-muted">MIA is working…</span>
                      </div>
                    )}
                    <div ref={endRef} />
                  </div>
                </div>
              )}
            </div>

            {/* Chat input — shown once chat has started */}
            {hasChat && (
              <div className="shrink-0 border-t border-hairline bg-paper px-6 py-4">
                <div className="mx-auto max-w-2xl space-y-3">
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={busy || uploadStatus === "uploading"}
                      title="Upload PDF, Excel, CSV, or DOCX"
                      className="flex items-center gap-1.5 rounded-xl border border-hairline bg-paper px-3 text-[12px] font-medium text-muted transition-colors hover:border-signal/30 hover:text-signal disabled:opacity-30"
                    >
                      <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                        <path d="M8 11V2M8 2L4.5 5.5M8 2l3.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
                        <path d="M2 13h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
                      </svg>
                      {uploadStatus === "uploading" ? "Reading…" : "Add file"}
                    </button>
                  </div>
                  {uploadError && (
                    <p className="text-[12px] text-red-500">{uploadError}</p>
                  )}
                  <div className="flex items-end gap-2 rounded-[20px] border border-hairline bg-mist p-1.5 transition-all focus-within:border-signal/40 focus-within:bg-paper focus-within:ring-4 focus-within:ring-signal/10">
                    <textarea
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          void send(input);
                        }
                      }}
                      rows={1}
                      placeholder="Provide missing values or ask MIA..."
                      className="max-h-32 flex-1 resize-none bg-transparent px-4 py-2.5 text-[14px] leading-relaxed text-ink placeholder:text-muted focus:outline-none"
                    />
                    <button
                      onClick={() => void send(input)}
                      disabled={busy || !input.trim()}
                      className="mb-0.5 mr-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-full bg-ink text-white transition-transform hover:scale-105 disabled:scale-100 disabled:opacity-25"
                      aria-label="Send message"
                    >
                      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                        <path
                          d="M8 13V3M8 3L3.5 7.5M8 3l4.5 4.5"
                          stroke="currentColor"
                          strokeWidth="1.8"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
            )}
          </section>
        </div>
      </div>
    </>
  );
}
