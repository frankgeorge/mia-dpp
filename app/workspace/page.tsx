"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import type {
  ChatMessage,
  EmailOutreach,
  FieldMapping,
  GraphEntry,
  DppPackage,
  ScrapeState,
} from "@/lib/standards/types";
import {
  buildDpp,
  missingRequired,
  NAMEPLATE_ELEMENTS,
  semanticIdFor,
  SUBMODELS,
  getElementsForSubmodel,
} from "@/lib/standards/idta";
import type { SubmodelId } from "@/lib/standards/idta";
import { MappingRow } from "@/components/MappingRow";
import { DppView } from "@/components/DppView";

const THRESHOLD = 0.85;
const GRAPH_KEY = "mia.graph.v1";
const SETTINGS_KEY = "mia.settings.v1";
const POLL_INTERVAL = 10_000;

const SAMPLES = [
  {
    label: "Pressure gauge",
    text: "Create a DPP for our AFRISO pressure gauge, model RF100-16, serial number 2024-8871, built 2024 at our Güglingen plant, protection class IP65, measuring range 0-16 bar, material number 63820.",
  },
  {
    label: "Rotary table",
    text: "DPP for a FIBRO rotary indexing table, type FB-320-NC, serial 887201-B, year of construction 2023, made in Weinsberg Germany, IP54, article nr 2470.12.320.",
  },
  {
    label: "Sparse data",
    text: "SCHUNK clamping module, order code JGZ-100-1, 2022.",
  },
];

interface OrgSettings {
  orgName: string;
  logoUrl: string;
  brandColor: string;
  sapHost: string;
  sapClient: string;
  sapUsername: string;
  sapPassword: string;
}

const SETTINGS_DEFAULTS: OrgSettings = {
  orgName: "",
  logoUrl: "",
  brandColor: "#0B5FD0",
  sapHost: "",
  sapClient: "100",
  sapUsername: "",
  sapPassword: "",
};

function loadSettings(): OrgSettings {
  if (typeof window === "undefined") return SETTINGS_DEFAULTS;
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    return raw ? { ...SETTINGS_DEFAULTS, ...JSON.parse(raw) } : SETTINGS_DEFAULTS;
  } catch {
    return SETTINGS_DEFAULTS;
  }
}

export default function Workspace() {
  // ── Core state ─────────────────────────────────────────────────────────────
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [mappings, setMappings] = useState<FieldMapping[]>([]);
  const [productName, setProductName] = useState("");
  const [dpp, setDpp] = useState<DppPackage | null>(null);
  const [graph, setGraph] = useState<GraphEntry[]>([]);
  const [mode, setMode] = useState<string>("");
  const [tab, setTab] = useState<"mappings" | "graph">("mappings");

  // ── Submodel selection ─────────────────────────────────────────────────────
  const [submodelId, setSubmodelId] = useState<SubmodelId>("nameplate");

  // ── URL scraping ───────────────────────────────────────────────────────────
  const [urlInput, setUrlInput] = useState("");
  const [scrape, setScrape] = useState<ScrapeState>({ phase: "idle" });

  // ── File upload ────────────────────────────────────────────────────────────
  const [uploading, setUploading] = useState(false);
  const [showAttachMenu, setShowAttachMenu] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const attachMenuRef = useRef<HTMLDivElement>(null);

  // ── Email outreach ─────────────────────────────────────────────────────────
  const [emailContact, setEmailContact] = useState("");
  const [sendingEmail, setSendingEmail] = useState(false);
  const [outreach, setOutreach] = useState<EmailOutreach | null>(null);
  const [showDraft, setShowDraft] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Settings drawer ────────────────────────────────────────────────────────
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settings, setSettings] = useState<OrgSettings>(loadSettings);
  const [settingsSaved, setSettingsSaved] = useState(false);
  const [sapTesting, setSapTesting] = useState(false);
  const [sapStatus, setSapStatus] = useState<"idle" | "ok" | "error">("idle");
  const [sapError, setSapError] = useState("");
  const [testMaterial, setTestMaterial] = useState("");

  const endRef = useRef<HTMLDivElement>(null);

  // ── Persist Integration Graph ──────────────────────────────────────────────
  useEffect(() => {
    try {
      const raw = localStorage.getItem(GRAPH_KEY);
      if (raw) setGraph(JSON.parse(raw));
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(GRAPH_KEY, JSON.stringify(graph));
    } catch { /* ignore */ }
  }, [graph]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  // Close attach menu on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (attachMenuRef.current && !attachMenuRef.current.contains(e.target as Node)) {
        setShowAttachMenu(false);
      }
    }
    if (showAttachMenu) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [showAttachMenu]);

  // ── Settings helpers ───────────────────────────────────────────────────────
  function setSetting(key: keyof OrgSettings, value: string) {
    setSettings((prev) => ({ ...prev, [key]: value }));
    setSettingsSaved(false);
  }

  function saveSettings() {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    setSettingsSaved(true);
    setTimeout(() => setSettingsSaved(false), 2000);
  }

  async function testSap() {
    if (!testMaterial.trim()) return;
    setSapTesting(true);
    setSapStatus("idle");
    setSapError("");
    try {
      const res = await fetch("/api/sap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sapHost: settings.sapHost,
          sapClient: settings.sapClient,
          username: settings.sapUsername,
          password: settings.sapPassword,
          materialNumber: testMaterial,
        }),
      });
      const data = await res.json();
      if (data.error) {
        setSapStatus("error");
        setSapError(data.error);
      } else {
        setSapStatus("ok");
      }
    } catch {
      setSapStatus("error");
      setSapError("Network error — could not reach the server.");
    } finally {
      setSapTesting(false);
    }
  }

  // ── Supplier response polling ──────────────────────────────────────────────
  const handleSupplierResponse = useCallback(
    (response: Record<string, string>) => {
      const newMappings: FieldMapping[] = Object.entries(response)
        .filter(([, v]) => v.trim())
        .map(([name, value], i) => ({
          id: `supplier-${Date.now()}-${i}`,
          sourceField: "SUPPLIER_RESPONSE",
          sourceValue: value,
          targetElement: name,
          semanticId: semanticIdFor(name),
          confidence: 0.8,
          reasoning:
            "Provided directly by the supplier via the MIA email request portal.",
          status: "review" as const,
        }));

      if (newMappings.length > 0) {
        setMappings((prev) => {
          const updated = [...prev];
          for (const nm of newMappings) {
            const idx = updated.findIndex(
              (m) => m.targetElement === nm.targetElement
            );
            if (idx >= 0) updated[idx] = nm;
            else updated.push(nm);
          }
          return updated;
        });

        setMessages((prev) => [
          ...prev,
          {
            role: "assistant" as const,
            content: `Supplier responded with ${newMappings.length} field${newMappings.length === 1 ? "" : "s"}: ${newMappings.map((m) => m.targetElement).join(", ")}. Review the new mappings below, then generate the passport.`,
          },
        ]);

        setOutreach((prev) => (prev ? { ...prev, responded: true } : prev));
        setTab("mappings");
      }

      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    },
    []
  );

  useEffect(() => {
    if (!outreach || outreach.responded) return;

    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/session/${outreach.token}`);
        if (!res.ok) return;
        const data = await res.json();
        if (data.responded && data.response) {
          handleSupplierResponse(data.response);
        }
      } catch { /* network blip — retry next tick */ }
    }, POLL_INTERVAL);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [outreach, handleSupplierResponse]);

  // ── Chat send ──────────────────────────────────────────────────────────────
  async function send(text: string) {
    const t = text.trim();
    if (!t || busy) return;

    const next: ChatMessage[] = [...messages, { role: "user", content: t }];
    setMessages(next);
    setInput("");
    setBusy(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: next, graph }),
      });
      const data = await res.json();
      setMode(data.mode ?? "");

      if (data.proposal) {
        applyProposal(data.proposal);
      }
      if (data.generate) generate();

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "That request didn't go through. Check your connection and send it again.",
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  // ── URL scraping ───────────────────────────────────────────────────────────
  async function scrapeUrl() {
    const url = urlInput.trim();
    if (!url || scrape.phase === "fetching" || scrape.phase === "extracting") return;

    setScrape({ phase: "fetching", url });
    setMessages((prev) => [
      ...prev,
      { role: "user", content: `Scrape this product page and extract all fields: ${url}` },
    ]);

    try {
      setScrape({ phase: "extracting", url });
      const res = await fetch("/api/scrape", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, graph }),
      });
      const data = await res.json();

      if (data.error) {
        setScrape({ phase: "error", url, error: data.error });
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: data.error },
        ]);
        return;
      }

      setMode(data.mode ?? "");
      setScrape({ phase: "done", url, pageTitle: data.pageTitle });
      setUrlInput("");

      if (data.proposal) {
        applyProposal(data.proposal);
      }

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply },
      ]);
    } catch {
      setScrape({ phase: "error", url, error: "Could not reach the scrape service." });
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Could not fetch that page. Check the URL or describe the product manually.",
        },
      ]);
    }
  }

  // ── File upload ────────────────────────────────────────────────────────────
  async function uploadFile(file: File) {
    if (uploading) return;
    setUploading(true);
    setShowAttachMenu(false);
    setMessages((prev) => [
      ...prev,
      { role: "user", content: `Uploaded file: ${file.name}` },
    ]);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("graph", JSON.stringify(graph));

    try {
      const res = await fetch("/api/upload", { method: "POST", body: formData });
      const data = await res.json();

      if (data.error) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: data.error },
        ]);
        return;
      }

      setMode(data.mode ?? "");
      if (data.proposal) applyProposal(data.proposal);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "File upload failed. Check your connection and try again." },
      ]);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  function applyProposal(proposal: { productName: string; mappings: any[] }) {
    setProductName(proposal.productName || "Product");
    setMappings(
      (proposal.mappings ?? []).map((m: any, i: number) => ({
        ...m,
        id: m.id ?? `${Date.now()}-${i}`,
        status: m.status ?? (m.confidence >= THRESHOLD ? "auto" : "review"),
      }))
    );
    setDpp(null);
    setTab("mappings");
  }

  // ── Email outreach ─────────────────────────────────────────────────────────
  async function sendEmail() {
    const email = emailContact.trim();
    if (!email || sendingEmail || gaps.length === 0) return;

    setSendingEmail(true);
    try {
      let branding: Record<string, string> | undefined;
      if (settings.orgName || settings.logoUrl || settings.brandColor) {
        branding = {
          orgName: settings.orgName,
          logoUrl: settings.logoUrl,
          brandColor: settings.brandColor,
        };
      }

      const res = await fetch("/api/email/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contactEmail: email,
          productName,
          productUrl: scrape.url ?? "",
          gaps,
          branding,
        }),
      });
      const data = await res.json();

      if (data.error && !data.token) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `Email failed: ${data.error}` },
        ]);
        return;
      }

      setOutreach({
        token: data.token,
        portalUrl: data.portalUrl,
        contactEmail: email,
        gaps,
        sent: data.sent,
        draft: data.draft,
        sentAt: new Date().toISOString(),
        responded: false,
      });

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.sent
            ? `Email sent to ${email}. MIA is now waiting for the supplier to fill in ${gaps.length} missing field${gaps.length > 1 ? "s" : ""}. I will automatically fill the mappings when they respond.`
            : `No email provider configured. Copy the draft below and send it manually to ${email}. Once they complete the form, MIA will automatically fill the missing fields.`,
        },
      ]);
    } finally {
      setSendingEmail(false);
    }
  }

  // ── Mapping decisions ──────────────────────────────────────────────────────
  function decide(id: string, status: "approved" | "rejected") {
    setMappings((prev) =>
      prev.map((m) => (m.id === id ? { ...m, status } : m))
    );
    const m = mappings.find((x) => x.id === id);
    if (m && status === "approved") writeToGraph(m);
  }

  function correct(id: string, targetElement: string) {
    setMappings((prev) =>
      prev.map((m) =>
        m.id === id
          ? {
              ...m,
              targetElement,
              semanticId:
                NAMEPLATE_ELEMENTS.find((e) => e.name === targetElement)
                  ?.semanticId ?? m.semanticId,
              status: "approved",
              reasoning: "Corrected by you, and saved to the Integration Graph.",
            }
          : m
      )
    );
    const m = mappings.find((x) => x.id === id);
    if (m) writeToGraph({ ...m, targetElement });
  }

  function writeToGraph(m: FieldMapping) {
    setGraph((prev) => {
      const i = prev.findIndex(
        (g) => g.sourceField.toLowerCase() === m.sourceField.toLowerCase()
      );
      const entry: GraphEntry = {
        sourceField: m.sourceField,
        targetElement: m.targetElement,
        semanticId: m.semanticId,
        verifiedAt: new Date().toISOString(),
        corrections: i >= 0 ? prev[i].corrections + 1 : 1,
      };
      if (i >= 0) {
        const copy = [...prev];
        copy[i] = entry;
        return copy;
      }
      return [entry, ...prev];
    });
  }

  function approveAll() {
    mappings
      .filter((m) => m.status === "review" || m.status === "auto")
      .forEach(writeToGraph);
    setMappings((prev) =>
      prev.map((m) =>
        m.status === "rejected" ? m : { ...m, status: "approved" }
      )
    );
  }

  function generate() {
    setMappings((cur) => {
      setDpp(buildDpp(productName || "Product", cur));
      return cur;
    });
  }

  // ── Derived counts ─────────────────────────────────────────────────────────
  const pending = mappings.filter((m) => m.status === "review").length;
  const ready = mappings.filter(
    (m) => m.status === "approved" || m.status === "auto"
  ).length;
  const gaps = missingRequired(mappings, submodelId);
  const isScraping =
    scrape.phase === "fetching" || scrape.phase === "extracting";

  // ── Input styles ───────────────────────────────────────────────────────────
  const drawerInputCls =
    "w-full rounded-xl border border-hairline bg-mist px-3 py-2.5 text-[13px] text-ink placeholder:text-muted focus:border-signal focus:outline-none";

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="flex h-screen flex-col bg-mist">
      {/* ── Top bar ──────────────────────────────────────────────────────── */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-hairline bg-paper px-5">
        <div className="flex items-center gap-3">
          <Link href="/" className="flex items-center gap-2">
            <span className="grid h-6 w-6 place-items-center rounded-md bg-ink">
              <span className="h-1.5 w-1.5 rounded-[1px] bg-white" />
            </span>
            <span className="text-[15px] font-semibold tracking-tight">MIA</span>
          </Link>
          <span className="hidden text-[13px] text-muted sm:inline">
            {productName || "New passport"}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {mode === "demo" && (
            <span className="rounded-full bg-mist px-2.5 py-1 font-mono text-[11px] text-muted">
              Demo mode
            </span>
          )}
          {mode === "live" && (
            <span className="rounded-full bg-signalDim px-2.5 py-1 font-mono text-[11px] text-signal">
              Live agent
            </span>
          )}
          <select
            value={submodelId}
            onChange={(e) => {
              setSubmodelId(e.target.value as SubmodelId);
              setMappings([]);
              setDpp(null);
            }}
            className="rounded-full border border-hairline bg-paper px-3 py-1.5 text-[12px] font-medium text-ink focus:outline-none"
          >
            {SUBMODELS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
          <button
            onClick={generate}
            disabled={ready === 0}
            className="rounded-full bg-ink px-4 py-1.5 text-[13px] font-medium text-white transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-30"
          >
            Generate passport
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* ── Chat panel ───────────────────────────────────────────────── */}
        <section className="flex min-h-0 flex-1 flex-col border-hairline bg-paper lg:max-w-[46%] lg:border-r">
          <div className="scroll-quiet flex-1 overflow-y-auto px-5 py-6">
            {messages.length === 0 && (
              <div className="mx-auto max-w-md pt-6">
                <h1 className="text-[26px] font-semibold leading-tight tracking-tight">
                  Describe or link a product.
                </h1>
                <p className="mt-2 text-[15px] leading-relaxed text-muted">
                  Paste a product page URL above to extract fields automatically,
                  or describe the product in the chat. MIA maps everything to
                  the IDTA Digital Nameplate and emails the supplier for anything
                  it cannot find.
                </p>
                <div className="mt-6 space-y-2">
                  {SAMPLES.map((s) => (
                    <button
                      key={s.label}
                      onClick={() => send(s.text)}
                      className="w-full rounded-xl border border-hairline p-3.5 text-left transition-colors hover:bg-mist"
                    >
                      <p className="text-[14px] font-medium">{s.label}</p>
                      <p className="mt-0.5 line-clamp-2 text-[13px] leading-relaxed text-muted">
                        {s.text}
                      </p>
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="mx-auto max-w-md space-y-4">
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={m.role === "user" ? "flex justify-end" : ""}
                >
                  <div
                    className={
                      m.role === "user"
                        ? "max-w-[85%] rounded-2xl rounded-br-md bg-signal px-4 py-2.5 text-[14px] leading-relaxed text-white"
                        : "max-w-[92%] text-[14px] leading-relaxed text-ink"
                    }
                  >
                    {m.content}
                  </div>
                </div>
              ))}

              {isScraping && (
                <div className="flex items-center gap-2.5 text-[13px] text-muted">
                  <span className="flex gap-1">
                    {[0, 1, 2].map((i) => (
                      <span
                        key={i}
                        className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted"
                        style={{ animationDelay: `${i * 140}ms` }}
                      />
                    ))}
                  </span>
                  {scrape.phase === "fetching"
                    ? "Fetching page..."
                    : "Extracting product fields..."}
                </div>
              )}

              {busy && !isScraping && (
                <div className="flex gap-1.5 py-1">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted"
                      style={{ animationDelay: `${i * 140}ms` }}
                    />
                  ))}
                </div>
              )}
              <div ref={endRef} />
            </div>
          </div>

          {/* ── Input area ───────────────────────────────────────────────── */}
          <div className="shrink-0 border-t border-hairline p-4 space-y-2">
            <div className="mx-auto max-w-md">
              {/* URL scrape bar */}
              <div className="flex items-center gap-2 rounded-2xl border border-hairline bg-mist px-3 py-2">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" className="shrink-0 text-muted">
                  <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.4" />
                  <path d="M8 1.5C8 1.5 5.5 4 5.5 8s2.5 6.5 2.5 6.5M8 1.5C8 1.5 10.5 4 10.5 8S8 14.5 8 14.5M1.5 8h13" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                </svg>
                <input
                  type="url"
                  value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") { e.preventDefault(); scrapeUrl(); }
                  }}
                  placeholder="Paste a product page URL to scrape..."
                  disabled={isScraping}
                  className="flex-1 bg-transparent text-[13px] placeholder:text-muted focus:outline-none disabled:opacity-50"
                />
                {scrape.phase === "done" && !isScraping && (
                  <span className="shrink-0 font-mono text-[10px] text-ok">scraped</span>
                )}
                {scrape.phase === "error" && !isScraping && (
                  <span className="shrink-0 font-mono text-[10px] text-warn">failed</span>
                )}
                <button
                  onClick={scrapeUrl}
                  disabled={!urlInput.trim() || isScraping}
                  className="shrink-0 rounded-xl bg-ink px-3 py-1.5 text-[12px] font-medium text-white transition-opacity hover:opacity-85 disabled:opacity-30"
                >
                  {isScraping ? "..." : "Scrape"}
                </button>
              </div>

              {/* Chat textarea + paperclip + send */}
              <div className="relative flex items-end gap-2 mt-2">
                {/* Hidden file input */}
                <input
                  ref={fileRef}
                  type="file"
                  accept=".pdf,.xlsx,.xls,.csv"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) uploadFile(f);
                  }}
                />

                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send(input);
                    }
                  }}
                  rows={1}
                  placeholder="Or describe the product in plain text..."
                  className="max-h-32 flex-1 resize-none rounded-2xl border border-hairline bg-paper px-4 py-3 pr-12 text-[14px] leading-relaxed placeholder:text-muted focus:border-signal focus:outline-none"
                />

                {/* Paperclip button — inside the textarea row, left of send */}
                <div className="absolute right-14 bottom-2" ref={attachMenuRef}>
                  <button
                    onClick={() => setShowAttachMenu((s) => !s)}
                    disabled={uploading}
                    className="grid h-8 w-8 place-items-center rounded-full text-muted transition-colors hover:bg-mist hover:text-ink disabled:opacity-40"
                    aria-label="Attach file"
                    title="Attach file"
                  >
                    {uploading ? (
                      <svg width="15" height="15" viewBox="0 0 16 16" fill="none" className="animate-spin">
                        <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" strokeDasharray="20 18" />
                      </svg>
                    ) : (
                      <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                        <path d="M13.5 7.5l-6 6a4 4 0 01-5.657-5.657l6.364-6.364a2.5 2.5 0 013.535 3.535L5.378 11.35a1 1 0 01-1.414-1.414L9.5 4.4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    )}
                  </button>

                  {/* Attach popup */}
                  {showAttachMenu && (
                    <div className="absolute bottom-10 right-0 z-50 w-44 rounded-2xl border border-hairline bg-paper shadow-lg overflow-hidden">
                      <p className="px-3 py-2 text-[11px] font-medium text-muted uppercase tracking-wide">
                        Attach file
                      </p>
                      <button
                        onClick={() => { setShowAttachMenu(false); fileRef.current?.click(); }}
                        className="flex w-full items-center gap-2.5 px-3 py-2.5 text-[13px] text-ink hover:bg-mist transition-colors"
                      >
                        <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                          <rect x="2" y="1" width="12" height="14" rx="2" stroke="currentColor" strokeWidth="1.4"/>
                          <path d="M5 5h6M5 8h6M5 11h3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                        </svg>
                        PDF / Excel / CSV
                      </button>
                    </div>
                  )}
                </div>

                {/* Send button */}
                <button
                  onClick={() => send(input)}
                  disabled={busy || !input.trim()}
                  className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-ink text-white transition-opacity hover:opacity-85 disabled:opacity-25"
                  aria-label="Send message"
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M8 13V3M8 3L3.5 7.5M8 3l4.5 4.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </section>

        {/* ── Right panel ──────────────────────────────────────────────── */}
        <section className="flex min-h-0 flex-1 flex-col bg-mist">
          <div className="flex shrink-0 items-center justify-between border-b border-hairline bg-paper px-5">
            <div className="flex">
              {(["mappings", "graph"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`relative px-3 py-3.5 text-[13px] font-medium capitalize transition-colors ${
                    tab === t ? "text-ink" : "text-muted hover:text-ink"
                  }`}
                >
                  {t === "graph" ? "Integration Graph" : "Mappings"}
                  {t === "graph" && graph.length > 0 && (
                    <span className="ml-1.5 rounded-full bg-mist px-1.5 py-0.5 font-mono text-[10px]">
                      {graph.length}
                    </span>
                  )}
                  {tab === t && (
                    <span className="absolute inset-x-3 -bottom-px h-0.5 rounded-full bg-ink" />
                  )}
                </button>
              ))}
            </div>
            {tab === "mappings" && pending > 0 && (
              <button
                onClick={approveAll}
                className="rounded-full border border-hairline px-3 py-1.5 text-[12px] font-medium transition-colors hover:bg-mist"
              >
                Approve all
              </button>
            )}
          </div>

          <div className="scroll-quiet min-h-0 flex-1 overflow-y-auto p-5">
            {tab === "mappings" ? (
              mappings.length === 0 ? (
                <Empty
                  title="No mappings yet"
                  body="Paste a product URL above to scrape it automatically, or describe the product in the chat."
                />
              ) : (
                <div className="space-y-4">
                  <div className="flex flex-wrap gap-2">
                    <Stat label="Ready" value={ready} tone="ok" />
                    <Stat label="Needs you" value={pending} tone="warn" />
                    <Stat label="Gaps" value={gaps.length} tone="plain" />
                  </div>

                  {gaps.length > 0 && (
                    <div className="rounded-xl border border-warn/25 bg-warn/[0.06] p-4 space-y-3">
                      <div>
                        <p className="text-[13px] font-medium text-warn">
                          Required elements still missing
                        </p>
                        <p className="mt-1 font-mono text-[12px] leading-relaxed text-ink/70">
                          {gaps.join(" · ")}
                        </p>
                      </div>

                      {!outreach ? (
                        <div className="rounded-lg border border-hairline bg-paper p-3.5">
                          <p className="text-[12px] font-medium text-ink">
                            Request missing data from supplier
                          </p>
                          <p className="mt-0.5 text-[12px] text-muted">
                            MIA will email them a link to a short form. When they
                            respond, the gaps fill automatically.
                          </p>
                          <div className="mt-2.5 flex gap-2">
                            <input
                              type="email"
                              value={emailContact}
                              onChange={(e) => setEmailContact(e.target.value)}
                              onKeyDown={(e) => { if (e.key === "Enter") sendEmail(); }}
                              placeholder="supplier@company.com"
                              className="flex-1 rounded-xl border border-hairline bg-mist px-3 py-2 text-[13px] placeholder:text-muted focus:border-signal focus:outline-none"
                            />
                            <button
                              onClick={sendEmail}
                              disabled={sendingEmail || !emailContact.trim()}
                              className="shrink-0 rounded-xl bg-ink px-3.5 py-2 text-[12px] font-medium text-white transition-opacity hover:opacity-85 disabled:opacity-30"
                            >
                              {sendingEmail ? "Sending..." : "Send request"}
                            </button>
                          </div>
                        </div>
                      ) : outreach.responded ? (
                        <div className="flex items-start gap-2.5 rounded-lg border border-ok/30 bg-ok/[0.06] p-3">
                          <span className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full bg-ok">
                            <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                              <path d="M1.5 4.5l1.5 1.5 3-3" stroke="white" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                          </span>
                          <div>
                            <p className="text-[12px] font-medium text-ok">Supplier responded</p>
                            <p className="mt-0.5 text-[12px] text-muted">
                              New mappings added below — review and approve them.
                            </p>
                          </div>
                        </div>
                      ) : (
                        <div className="rounded-lg border border-hairline bg-paper p-3.5">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span className="flex gap-0.5">
                                {[0, 1, 2].map((i) => (
                                  <span
                                    key={i}
                                    className="h-1 w-1 animate-pulse rounded-full bg-signal"
                                    style={{ animationDelay: `${i * 200}ms` }}
                                  />
                                ))}
                              </span>
                              <p className="text-[12px] font-medium text-ink">Waiting for supplier</p>
                            </div>
                            <a
                              href={outreach.portalUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-[11px] text-signal underline underline-offset-2"
                            >
                              View portal
                            </a>
                          </div>
                          <p className="mt-1 text-[12px] text-muted">
                            {outreach.sent
                              ? `Email sent to ${outreach.contactEmail}. Checking for reply every 10 s.`
                              : `No email provider — send the draft manually to ${outreach.contactEmail}.`}
                          </p>
                          <div className="mt-2.5 flex items-center gap-2 rounded-lg border border-hairline bg-mist px-3 py-2">
                            <p className="flex-1 truncate font-mono text-[10px] text-muted">
                              {outreach.portalUrl}
                            </p>
                            <button
                              onClick={() => navigator.clipboard.writeText(outreach.portalUrl)}
                              className="shrink-0 rounded-md border border-hairline bg-paper px-2 py-1 text-[10px] text-ink transition-colors hover:bg-mist"
                            >
                              Copy
                            </button>
                          </div>
                          {outreach.draft && (
                            <div className="mt-2">
                              <button
                                onClick={() => setShowDraft((s) => !s)}
                                className="text-[11px] text-muted underline underline-offset-2"
                              >
                                {showDraft ? "Hide" : "Show"} email draft
                              </button>
                              {showDraft && (
                                <pre className="scroll-quiet mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded-lg border border-hairline bg-mist p-3 font-mono text-[10px] leading-relaxed text-ink/70">
                                  {outreach.draft}
                                </pre>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  <div className="space-y-2">
                    {mappings.map((m) => (
                      <MappingRow
                        key={m.id}
                        mapping={m}
                        onDecide={decide}
                        onCorrect={correct}
                      />
                    ))}
                  </div>

                  {dpp && <DppView dpp={dpp} />}
                </div>
              )
            ) : graph.length === 0 ? (
              <Empty
                title="The graph is empty"
                body="Approve or correct a mapping and it gets saved here. The next product that uses the same field starts from your decision."
              />
            ) : (
              <div className="space-y-2">
                <p className="pb-1 text-[13px] leading-relaxed text-muted">
                  Verified mappings reused across products. These raise MIA&rsquo;s
                  confidence on the next passport.
                </p>
                {graph.map((g) => (
                  <div
                    key={g.sourceField}
                    className="rounded-xl border border-hairline bg-paper p-3.5"
                  >
                    <p className="font-mono text-[13px]">
                      {g.sourceField}{" "}
                      <span className="text-muted">&rarr;</span>{" "}
                      <span className="text-signal">{g.targetElement}</span>
                    </p>
                    <p className="mt-1 font-mono text-[11px] text-muted">
                      {g.semanticId} &middot; verified {g.corrections}&times;
                    </p>
                  </div>
                ))}
                <button
                  onClick={() => setGraph([])}
                  className="mt-2 text-[12px] text-muted underline underline-offset-2 hover:text-ink"
                >
                  Clear graph
                </button>
              </div>
            )}
          </div>
        </section>
      </div>

      {/* ── Settings drawer toggle — bottom left ──────────────────────────── */}
      <button
        onClick={() => setSettingsOpen(true)}
        className="fixed bottom-5 left-5 z-40 flex h-9 w-9 items-center justify-center rounded-full border border-hairline bg-paper shadow-md transition-colors hover:bg-mist"
        aria-label="Open settings"
        title="Settings"
      >
        {/* Chevron right arrow */}
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
          <path d="M6 4l4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {/* ── Settings drawer overlay ───────────────────────────────────────── */}
      {settingsOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/20 backdrop-blur-[2px]"
          onClick={() => setSettingsOpen(false)}
        />
      )}

      {/* ── Settings drawer panel ─────────────────────────────────────────── */}
      <div
        className={`fixed bottom-0 left-0 top-0 z-50 flex w-80 flex-col bg-paper shadow-2xl transition-transform duration-300 ease-in-out ${
          settingsOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Drawer header */}
        <div className="flex shrink-0 items-center justify-between border-b border-hairline px-5 py-4">
          <div className="flex items-center gap-2.5">
            {/* Gear icon */}
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="text-ink">
              <circle cx="8" cy="8" r="2.5" stroke="currentColor" strokeWidth="1.4"/>
              <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.05 3.05l1.41 1.41M11.54 11.54l1.41 1.41M3.05 12.95l1.41-1.41M11.54 4.46l1.41-1.41" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
            </svg>
            <span className="text-[15px] font-semibold tracking-tight">Settings</span>
          </div>
          <button
            onClick={() => setSettingsOpen(false)}
            className="grid h-7 w-7 place-items-center rounded-full text-muted transition-colors hover:bg-mist hover:text-ink"
            aria-label="Close settings"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <path d="M1 1l10 10M11 1L1 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </button>
        </div>

        {/* Drawer content — scrollable */}
        <div className="scroll-quiet flex-1 overflow-y-auto px-5 py-5 space-y-6">

          {/* Branding section */}
          <div className="space-y-4">
            <div>
              <p className="text-[13px] font-semibold text-ink">Supplier portal branding</p>
              <p className="mt-0.5 text-[11px] leading-relaxed text-muted">
                Customise how your supplier portal looks when MIA requests missing data.
              </p>
            </div>
            <div className="space-y-1.5">
              <label className="block text-[12px] font-medium text-ink">Organisation name</label>
              <input
                type="text"
                value={settings.orgName}
                onChange={(e) => setSetting("orgName", e.target.value)}
                placeholder="Acme Manufacturing GmbH"
                className={drawerInputCls}
              />
            </div>
            <div className="space-y-1.5">
              <label className="block text-[12px] font-medium text-ink">Logo URL</label>
              <input
                type="url"
                value={settings.logoUrl}
                onChange={(e) => setSetting("logoUrl", e.target.value)}
                placeholder="https://yourcompany.com/logo.png"
                className={drawerInputCls}
              />
              {settings.logoUrl && (
                <img
                  src={settings.logoUrl}
                  alt="Logo preview"
                  className="mt-1.5 h-8 rounded object-contain"
                  onError={(e) => ((e.target as HTMLImageElement).style.display = "none")}
                />
              )}
            </div>
            <div className="space-y-1.5">
              <label className="block text-[12px] font-medium text-ink">Brand colour</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={settings.brandColor}
                  onChange={(e) => setSetting("brandColor", e.target.value)}
                  className="h-8 w-12 cursor-pointer rounded-lg border border-hairline p-0.5"
                />
                <input
                  type="text"
                  value={settings.brandColor}
                  onChange={(e) => setSetting("brandColor", e.target.value)}
                  className={`${drawerInputCls} flex-1 font-mono text-[12px]`}
                />
              </div>
            </div>
          </div>

          <div className="border-t border-hairline" />

          {/* SAP connector section */}
          <div className="space-y-4">
            <div>
              <p className="text-[13px] font-semibold text-ink">SAP OData connector</p>
              <p className="mt-0.5 text-[11px] leading-relaxed text-muted">
                Connect to SAP to pull material master data. Supports S/4HANA and ECC.
              </p>
            </div>
            <div className="space-y-1.5">
              <label className="block text-[12px] font-medium text-ink">SAP hostname</label>
              <input
                type="url"
                value={settings.sapHost}
                onChange={(e) => setSetting("sapHost", e.target.value)}
                placeholder="https://your-sap.company.com"
                className={drawerInputCls}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="block text-[12px] font-medium text-ink">Client</label>
                <input
                  type="text"
                  value={settings.sapClient}
                  onChange={(e) => setSetting("sapClient", e.target.value)}
                  placeholder="100"
                  className={drawerInputCls}
                />
              </div>
              <div className="space-y-1.5">
                <label className="block text-[12px] font-medium text-ink">Username</label>
                <input
                  type="text"
                  value={settings.sapUsername}
                  onChange={(e) => setSetting("sapUsername", e.target.value)}
                  placeholder="MIA_READ"
                  className={drawerInputCls}
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <label className="block text-[12px] font-medium text-ink">Password</label>
              <input
                type="password"
                value={settings.sapPassword}
                onChange={(e) => setSetting("sapPassword", e.target.value)}
                placeholder="••••••••"
                className={drawerInputCls}
              />
            </div>

            {/* Test SAP */}
            <div className="flex items-center gap-2 rounded-xl border border-hairline bg-mist px-3 py-2.5">
              <input
                type="text"
                value={testMaterial}
                onChange={(e) => setTestMaterial(e.target.value)}
                placeholder="Material number to test"
                className="flex-1 bg-transparent text-[12px] focus:outline-none"
              />
              <button
                onClick={testSap}
                disabled={sapTesting || !settings.sapHost || !testMaterial.trim()}
                className="shrink-0 rounded-xl bg-ink px-3 py-1.5 text-[11px] font-medium text-white transition-opacity hover:opacity-85 disabled:opacity-30"
              >
                {sapTesting ? "..." : "Test"}
              </button>
            </div>
            {sapStatus === "ok" && (
              <p className="text-[12px] text-ok">SAP connection successful.</p>
            )}
            {sapStatus === "error" && (
              <p className="text-[12px] text-warn">{sapError}</p>
            )}
          </div>
        </div>

        {/* Drawer footer — save button */}
        <div className="shrink-0 border-t border-hairline px-5 py-4">
          <button
            onClick={saveSettings}
            className="w-full rounded-full bg-ink py-2.5 text-[13px] font-semibold text-white transition-opacity hover:opacity-85"
          >
            {settingsSaved ? "Saved!" : "Save settings"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Small helper components ─────────────────────────────────────────────────

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "ok" | "warn" | "plain";
}) {
  const cls =
    tone === "ok" ? "text-ok" : tone === "warn" ? "text-warn" : "text-muted";
  return (
    <div className="rounded-lg border border-hairline bg-paper px-3 py-2">
      <span className={`font-mono text-[15px] tabular-nums ${cls}`}>{value}</span>
      <span className="ml-1.5 text-[12px] text-muted">{label}</span>
    </div>
  );
}

function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="mx-auto max-w-xs pt-16 text-center">
      <p className="text-[15px] font-medium">{title}</p>
      <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{body}</p>
    </div>
  );
}
