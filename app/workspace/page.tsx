"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useUser } from "@clerk/nextjs";
import type {
  AgentTraceEvent,
  AgentReviewDecision,
  AgentResponse,
  CompanyCandidate,
  ChatMessage,
  CoverageReport,
  DppPackage,
  EvidenceRecord,
  FieldMapping,
  HumanRequest,
  MappingResult,
  Requirement,
  SemanticReviewItem,
  ProductCandidate,
  WorkspaceArtifact,
  MappingKnowledgeEntry,
} from "@/lib/types";
import { CoveragePanel } from "@/components/CoveragePanel";
import { EvidencePanel } from "@/components/EvidencePanel";
import { MappingReviewRow, MappingRow } from "@/components/MappingRow";
import { DppView } from "@/components/DppView";
import { AgentActivity } from "@/components/AgentActivity";
import { ChatMarkdown } from "@/components/ChatMarkdown";
import { LiveActivity } from "@/components/LiveActivity";
import { WorkspaceExplorer } from "@/components/WorkspaceExplorer";
import { IntegrationGraph } from "@/components/IntegrationGraph";
import { OnboardingModal } from "@/components/OnboardingModal";

const API_URL = process.env.NEXT_PUBLIC_MIA_API_URL ?? "";
type WorkspaceTab =
  | "mappings"
  | "evidence"
  | "coverage"
  | "process"
  | "data"
  | "graph";

const SAMPLES = [
  {
    label: "Pressure gauge",
    text: "Create a DPP for our AFRISO pressure gauge, model RF100-16, serial number 2024-8871, built 2024 at our Guglingen plant, protection class IP65, measuring range 0-16 bar, material number 63820.",
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
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [mappings, setMappings] = useState<FieldMapping[]>([]);
  const [productName, setProductName] = useState("");
  const [dpp, setDpp] = useState<DppPackage | null>(null);
  const [evidence, setEvidence] = useState<EvidenceRecord[]>([]);
  const [mappingResult, setMappingResult] = useState<MappingResult | null>(null);
  const [coverageReport, setCoverageReport] = useState<CoverageReport | null>(null);
  const [mappingKnowledge, setMappingKnowledge] = useState<MappingKnowledgeEntry[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [agentStatus, setAgentStatus] = useState<AgentResponse["status"]>("completed");
  const [companyCandidates, setCompanyCandidates] = useState<CompanyCandidate[]>([]);
  const [productCandidates, setProductCandidates] = useState<ProductCandidate[]>([]);
  const [currentProductId, setCurrentProductId] = useState<string | null>(null);
  const [mappingCycleId, setMappingCycleId] = useState<string | null>(null);
  const [agentActivity, setAgentActivity] = useState<AgentTraceEvent[]>([]);
  const [artifacts, setArtifacts] = useState<WorkspaceArtifact[]>([]);
  const [semanticReview, setSemanticReview] = useState<SemanticReviewItem[]>([]);
  const [humanRequest, setHumanRequest] = useState<HumanRequest | null>(null);
  const [humanValue, setHumanValue] = useState("");
  const [reviewDecisions, setReviewDecisions] = useState<
    Record<string, AgentReviewDecision>
  >({});
  const [tab, setTab] = useState<WorkspaceTab>("mappings");
  const [panelOpen, setPanelOpen] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  // ── Deploy state ──────────────────────────────────────────────────────────
  const [deployStatus, setDeployStatus] = useState<"idle" | "deploying" | "deployed" | "error">("idle");
  const [deployResult, setDeployResult] = useState<{
    passport_url: string;
    qr_code_png_b64: string;
    shell_ids: string[];
  } | null>(null);
  const [deployError, setDeployError] = useState("");

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

  // Poll for supplier response every 10 s after email is sent
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
    if (!supplierEmail || gaps.length === 0) return;
    setOutreachStatus("sending");
    setOutreachError("");
    try {
      const res = await fetch("/api/email/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contactEmail: supplierEmail,
          productName: productName || "Product",
          productUrl: websiteUrl || "",
          gaps,
        }),
      });
      const data = (await res.json()) as { token?: string; portalUrl?: string; sent?: boolean; error?: string };
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

  const mergeActivity = useCallback((events: AgentTraceEvent[]) => {
    setAgentActivity((previous) => {
      const known = new Set(previous.map((event) => event.id));
      return [...previous, ...events.filter((event) => !known.has(event.id))];
    });
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy, agentActivity]);

  useEffect(() => {
    const load = async () => {
      try {
        const response = await fetch(`${API_URL}/api/mapping-knowledge`);
        if (response.ok) {
          setMappingKnowledge((await response.json()) as MappingKnowledgeEntry[]);
        }
      } catch {
        /* The empty state remains usable while the backend is unavailable. */
      }
    };
    void load();
  }, []);

  useEffect(() => {
    if (!busy || !threadId) return;
    let cancelled = false;
    const poll = async () => {
      const response = await fetch(
        `${API_URL}/api/workspaces/${encodeURIComponent(threadId)}/trace`
      );
      if (!cancelled && response.ok) {
        mergeActivity((await response.json()) as AgentTraceEvent[]);
      }
    };
    void poll();
    const interval = window.setInterval(() => void poll(), 1000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [busy, threadId, mergeActivity]);

  function activeThread(): string {
    const active = threadId ?? `thread-${crypto.randomUUID()}`;
    if (!threadId) setThreadId(active);
    return active;
  }

  async function send(text: string) {
    const t = text.trim();
    if (!t || busy) return;

    const next: ChatMessage[] = [...messages, { role: "user", content: t }];
    setMessages(next);
    setInput("");
    const activeThreadId = activeThread();
    setBusy(true);

    try {
      const res = await fetch(`${API_URL}/api/agent/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ threadId: activeThreadId, message: t }),
      });
      const body = (await res.json()) as AgentResponse | { detail?: string };
      if (!res.ok) {
        throw new Error("detail" in body && body.detail ? body.detail : `Python backend returned ${res.status}`);
      }
      const data = body as AgentResponse;
      applyAgentResponse(data);

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

  async function ingestWebsite() {
    const url = websiteUrl.trim();
    if (!url || busy || semanticReview.length > 0) return;
    const activeThreadId = activeThread();
    setBusy(true);
    setMessages((previous) => [
      ...previous,
      { role: "user", content: `Import product website: ${url}` },
    ]);

    try {
      const response = await fetch(`${API_URL}/api/agent/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          threadId: activeThreadId,
          message: `Import product website: ${url}`,
        }),
      });
      const responseText = await response.text();
      let body: unknown;
      try {
        body = JSON.parse(responseText) as unknown;
      } catch {
        body = { detail: responseText || `Python backend returned ${response.status}` };
      }
      if (!response.ok) {
        const detail =
          typeof body === "object" &&
          body !== null &&
          "detail" in body &&
          typeof body.detail === "string"
            ? body.detail
            : null;
        throw new Error(
          detail ?? `Python backend returned ${response.status}`
        );
      }
      const data = body as AgentResponse;
      applyAgentResponse(data);
      setWebsiteUrl("");
      setMessages((previous) => [
        ...previous,
        { role: "assistant", content: data.reply },
      ]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      setMessages((previous) => [
        ...previous,
        {
          role: "assistant",
          content: `The product website could not be imported: ${message}`,
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  function applyAgentResponse(data: AgentResponse) {
    setThreadId(data.threadId);
    setAgentStatus(data.status);
    setCompanyCandidates(data.companyCandidates);
    setProductCandidates(data.productCandidates);
    setCurrentProductId(data.currentProduct?.productId ?? null);
    setHumanRequest(data.pendingHumanRequest);
    mergeActivity(data.traceEvents);
    void refreshArtifacts(data.threadId);
    void refreshMappingKnowledge();
    const product = data.currentProduct;
    if (product?.mappingResult && product.coverageReport) {
      applyWebsiteResult(
        product,
        product.pendingReviews,
        data.status === "awaiting_review"
      );
    }
  }

  async function submitHumanValue() {
    if (!threadId || !humanRequest?.requirementId || !humanValue.trim() || busy) return;
    setBusy(true);
    try {
      const response = await fetch(`${API_URL}/api/agent/value`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          threadId,
          productId: humanRequest.productId,
          requirementId: humanRequest.requirementId,
          value: humanValue.trim(),
        }),
      });
      const body = (await response.json()) as AgentResponse | { detail?: string };
      if (!response.ok) {
        throw new Error("detail" in body && body.detail ? body.detail : "Value was rejected");
      }
      const data = body as AgentResponse;
      applyAgentResponse(data);
      setHumanValue("");
      setMessages((previous) => [
        ...previous,
        { role: "user", content: humanValue.trim() },
        { role: "assistant", content: data.reply },
      ]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      setMessages((previous) => [
        ...previous,
        { role: "assistant", content: `The value could not be saved: ${message}` },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function refreshArtifacts(activeThreadId: string) {
    const response = await fetch(
      `${API_URL}/api/workspaces/${encodeURIComponent(activeThreadId)}/artifacts`
    );
    if (response.ok) setArtifacts((await response.json()) as WorkspaceArtifact[]);
  }

  async function refreshMappingKnowledge() {
    const response = await fetch(`${API_URL}/api/mapping-knowledge`);
    if (response.ok) {
      setMappingKnowledge((await response.json()) as MappingKnowledgeEntry[]);
    }
  }

  function applyWebsiteResult(
    product: NonNullable<AgentResponse["currentProduct"]>,
    reviewItems: SemanticReviewItem[],
    awaitingReview: boolean
  ) {
    const resolvedMappings = [
      ...(product.mappingResult?.mapped ?? []),
      ...(product.mappingResult?.ambiguous ?? []),
      ...(product.mappingResult?.rejected ?? []),
    ];
    const resolvedIds = new Set(resolvedMappings.map((mapping) => mapping.id));
    const semantic = reviewItems
      .flatMap((item) => item.mapping ? [item.mapping] : [])
      .filter((mapping) => !resolvedIds.has(mapping.id));
    setProductName(product.productName || product.candidate?.name || "Website product");
    setMappingCycleId(product.mappingCycleId);
    setMappings([...resolvedMappings, ...semantic]);
    setSemanticReview(awaitingReview ? reviewItems : []);
    setReviewDecisions(
      awaitingReview
        ? Object.fromEntries(
            reviewItems
              .filter((item) => item.status !== "uncertain")
              .map((item) => [item.id, { reviewId: item.id, decision: "keep" }])
          )
        : {}
    );
    setEvidence(product.evidence);
    setMappingResult(product.mappingResult);
    setCoverageReport(product.coverageReport);
    setDpp(null);
    setTab("mappings");
    setPanelOpen(true);
  }

  async function confirmSemanticReview() {
    if (!threadId || semanticReview.length === 0 || busy) return;
    const decisions = semanticReview.flatMap((item) => {
      const decision = reviewDecisions[item.id];
      return decision ? [decision] : [];
    });
    const invalid =
      decisions.length !== semanticReview.length ||
      decisions.some(
        (decision) =>
          decision.decision === "change_target" && !decision.correctedRequirementId
      );
    if (invalid) return;

    setBusy(true);
    try {
      if (!currentProductId) throw new Error("No active product is available for review.");
      const response = await fetch(`${API_URL}/api/agent/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          threadId,
          productId: currentProductId,
          mappingCycleId,
          decisions,
        }),
      });
      const body = (await response.json()) as AgentResponse | { detail?: string };
      if (!response.ok) {
        throw new Error("detail" in body && body.detail ? body.detail : `Python backend returned ${response.status}`);
      }
      const data = body as AgentResponse;
      applyAgentResponse(data);
      setReviewDecisions({});
      setMessages((previous) => [
        ...previous,
        { role: "assistant", content: data.reply },
      ]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      setMessages((previous) => [
        ...previous,
        { role: "assistant", content: `The semantic review could not be saved: ${message}` },
      ]);
    } finally {
      setBusy(false);
    }
  }

  function decide(id: string, status: "approved" | "rejected", comment?: string) {
    setMappings((prev) =>
      prev.map((m) => (m.id === id ? { ...m, status } : m))
    );
    const review = semanticReview.find((item) => item.mapping?.id === id);
    if (review) {
      setReviewDecisions((previous) => ({
        ...previous,
        [review.id]: {
          reviewId: review.id,
          decision: status === "approved" ? "keep" : "reject",
          comment: comment?.trim() || null,
        },
      }));
    }
  }

  function correct(
    id: string,
    selected: Requirement,
    correctedValue?: string,
    comment?: string
  ) {
    const mapping = mappings.find((item) => item.id === id);
    if (!mapping) return;
    const corrected: FieldMapping = {
      ...mapping,
      target: {
        templateKey: selected.templateKey,
        templateRelease: selected.templateRelease,
        templatePath: selected.templatePath,
        instancePath: selected.templatePath,
        idShort: selected.idShort ?? selected.templatePath.at(-1) ?? "Target",
        semanticId: selected.semanticId!,
      },
      sourceValue: correctedValue?.trim() || mapping.sourceValue,
      status: "approved",
      mappingOrigin: "human",
      humanReviewed: true,
      humanComment: comment?.trim() || null,
      reasoning: "Corrected by you and awaiting trusted backend persistence.",
    };
    setMappings((previous) =>
      previous.map((item) => (item.id === id ? corrected : item))
    );
    const review = semanticReview.find((item) => item.mapping?.id === id);
    if (review) {
      setReviewDecisions((previous) => ({
        ...previous,
        [review.id]: {
          reviewId: review.id,
          decision: "change_target",
          correctedRequirementId: selected.id,
          correctedValue: correctedValue?.trim() || null,
          comment: comment?.trim() || null,
        },
      }));
    }
  }

  function approveAll() {
    setMappings((prev) =>
      prev.map((m) =>
        m.status === "rejected" ? m : { ...m, status: "approved" }
      )
    );
    setReviewDecisions((previous) => {
      const next = { ...previous };
      for (const item of semanticReview) {
        next[item.id] = { reviewId: item.id, decision: "keep" };
      }
      return next;
    });
  }

  async function generate(
    selectedProduct = productName,
    selectedMappings = mappings,
    selectedEvidence = evidence
  ) {
    try {
      const response = await fetch(`${API_URL}/api/dpp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          productName: selectedProduct || "Product",
          mappings: selectedMappings,
          evidence: selectedEvidence,
        }),
      });
      if (!response.ok) {
        throw new Error(`Python backend returned ${response.status}`);
      }
      setDpp(await response.json());
    } catch {
      setMessages((previous) => [
        ...previous,
        {
          role: "assistant",
          content:
            "The Python backend could not build the passport. Check that it is running and try again.",
        },
      ]);
    }
  }

  async function deployPassport() {
    if (!threadId || deployStatus === "deploying") return;
    setDeployStatus("deploying");
    setDeployError("");
    try {
      const res = await fetch(`${API_URL}/api/workspaces/${threadId}/deploy`, {
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
        detail?: string;
      };
      if (!res.ok) {
        throw new Error(body.detail ?? `Deploy failed: ${res.status}`);
      }
      setDeployResult({
        passport_url: body.passport_url ?? "",
        qr_code_png_b64: body.qr_code_png_b64 ?? "",
        shell_ids: body.shell_ids ?? [],
      });
      setDeployStatus("deployed");
    } catch (error) {
      setDeployError(error instanceof Error ? error.message : "Deployment failed.");
      setDeployStatus("error");
    }
  }

  const pending = mappings.filter((m) => m.status === "review").length;
  const ready = mappings.filter(
    (m) => m.status === "approved" || m.status === "auto"
  ).length;
  const websiteAutoMapped =
    mappingResult?.mapped.filter((mapping) => mapping.status === "auto")
      .length ?? 0;
  const websiteNeedsReview = mappingResult
    ? mappingResult.ambiguous.length +
      mappingResult.mapped.filter((mapping) => mapping.status === "review")
        .length +
      semanticReview.filter(
        (item) =>
          item.status === "uncertain" || item.mapping?.status === "review"
      ).length
    : 0;
  const gaps = coverageReport
    ? coverageReport.coverage.flatMap((item) => {
        const requirement = coverageReport.inventory.requirements.find(
          (candidate) => candidate.id === item.requirementId
        );
        return item.status === "missing" && requirement?.required
          ? [requirement.idShort ?? requirement.templatePath.at(-1) ?? requirement.id]
          : [];
      })
    : [];
  const correctionTargets =
    coverageReport?.inventory.requirements.filter(
      (item) => item.kind === "value" && !item.wildcard && item.semanticId
    ) ?? [];

  const hasChat = messages.length > 0;
  const firstName = user?.firstName ?? user?.username ?? "";

  return (
    <>
      {showOnboarding && (
        <OnboardingModal onClose={() => setShowOnboarding(false)} />
      )}

      <div className="flex h-full flex-col">
        {/* Top bar — only shown when there is chat activity */}
        {hasChat && (
          <header className="shrink-0 flex h-14 items-center justify-between border-b border-hairline bg-paper px-6">
            <span className="text-[14px] font-medium text-ink truncate">
              {productName || "New passport"}
            </span>
            <div className="flex items-center gap-3">
              {ready > 0 && (
                <button
                  onClick={() => void generate()}
                  className="rounded-full bg-ink px-4 py-1.5 text-[13px] font-medium text-white transition-all hover:shadow-md hover:-translate-y-px"
                >
                  Generate passport
                </button>
              )}
            </div>
          </header>
        )}

        <div className="flex min-h-0 flex-1">
          {/* Chat column */}
          <section className="flex min-h-0 flex-1 flex-col">
            {/* Messages / empty state */}
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

                    {/* Main chat input */}
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
                          placeholder="Describe a product or paste a URL..."
                          className="max-h-40 flex-1 resize-none bg-transparent px-4 py-2.5 text-[14px] leading-relaxed text-ink placeholder:text-muted focus:outline-none"
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

                    {/* Quick starts */}
                    <div className="mt-5">
                      <p className="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
                        Quick starts
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {SAMPLES.map((s) => (
                          <button
                            key={s.label}
                            onClick={() => void send(s.text)}
                            className="rounded-full border border-hairline bg-paper px-4 py-2 text-[13px] font-medium text-ink transition-all hover:border-signal/30 hover:bg-signalDim hover:text-signal"
                          >
                            {s.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Recent assets */}
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

                    {agentStatus === "awaiting_company" && companyCandidates.length > 0 && !busy && (
                      <div className="space-y-2">
                        <p className="text-xs font-medium uppercase tracking-wide text-muted">
                          Select the company
                        </p>
                        {companyCandidates.map((candidate) => (
                          <button
                            key={candidate.id}
                            onClick={() => void send(`Select company ${candidate.id}: ${candidate.name}`)}
                            className="w-full rounded-xl border border-hairline bg-paper p-3 text-left hover:border-signal/40"
                          >
                            <p className="text-sm font-semibold text-ink">{candidate.name}</p>
                            <p className="mt-1 text-xs text-muted">{candidate.domain}</p>
                            {candidate.description && (
                              <p className="mt-1 line-clamp-2 text-xs text-muted">
                                {candidate.description}
                              </p>
                            )}
                          </button>
                        ))}
                      </div>
                    )}

                    {agentStatus === "awaiting_product" && productCandidates.length > 0 && !busy && (
                      <div className="space-y-2">
                        <p className="text-xs font-medium uppercase tracking-wide text-muted">
                          Select a product
                        </p>
                        {productCandidates.map((candidate) => (
                          <button
                            key={candidate.id}
                            onClick={() => void send(`Select product ${candidate.id}: ${candidate.name}`)}
                            className="w-full rounded-xl border border-hairline bg-paper p-3 text-left hover:border-signal/40"
                          >
                            <p className="text-sm font-semibold text-ink">{candidate.name}</p>
                            <p className="mt-1 line-clamp-2 text-xs text-muted">
                              {candidate.description || candidate.officialUrl}
                            </p>
                          </button>
                        ))}
                      </div>
                    )}

                    {agentStatus === "awaiting_optional_choice" && !busy && (
                      <div className="flex flex-wrap gap-2">
                        <button
                          onClick={() => void send("Continue with current data")}
                          className="rounded-full bg-ink px-4 py-2 text-[12px] font-medium text-white"
                        >
                          Continue with current data
                        </button>
                        <button
                          onClick={() => void send("Add optional information")}
                          className="rounded-full border border-hairline bg-paper px-4 py-2 text-[12px] font-medium text-ink"
                        >
                          Add optional information
                        </button>
                      </div>
                    )}

                    {humanRequest?.kind === "requirement_value" && !busy && (
                      <form
                        onSubmit={(event) => {
                          event.preventDefault();
                          void submitHumanValue();
                        }}
                        className="rounded-xl border border-warn/20 bg-paper p-4"
                      >
                        <p className="text-sm font-medium text-ink">{humanRequest.summary}</p>
                        <div className="mt-3 flex gap-2">
                          <input
                            value={humanValue}
                            onChange={(event) => setHumanValue(event.target.value)}
                            className="min-w-0 flex-1 rounded-lg border border-hairline px-3 py-2 text-sm"
                            placeholder="Enter the verified value"
                          />
                          <button
                            type="submit"
                            disabled={!humanValue.trim()}
                            className="rounded-lg bg-ink px-4 py-2 text-xs font-medium text-white disabled:opacity-30"
                          >
                            Save value
                          </button>
                        </div>
                      </form>
                    )}

                    {busy && <LiveActivity events={agentActivity} />}
                    <div ref={endRef} />
                  </div>
                </div>
              )}
            </div>

            {/* Chat input — always shown once chat has started */}
            {hasChat && (
              <div className="shrink-0 border-t border-hairline bg-paper px-6 py-4">
                <div className="mx-auto max-w-2xl space-y-3">
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      void ingestWebsite();
                    }}
                  >
                    <div className="flex gap-2">
                      <input
                        type="url"
                        required
                        value={websiteUrl}
                        onChange={(event) => setWebsiteUrl(event.target.value)}
                        placeholder="https://manufacturer.com/products/model"
                        className="min-w-0 flex-1 rounded-xl border border-hairline bg-mist px-3 py-2 text-[13px] text-ink shadow-sm placeholder:text-muted focus:border-signal focus:outline-none focus:ring-4 focus:ring-signal/10"
                      />
                      <button
                        type="submit"
                        disabled={busy || semanticReview.length > 0 || !websiteUrl.trim()}
                        className="rounded-xl border border-signal/30 bg-signalDim px-3 text-[12px] font-medium text-signal transition-colors hover:bg-signal/15 disabled:opacity-30"
                      >
                        Import URL
                      </button>
                    </div>
                  </form>
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
                      placeholder="Ask MIA, clarify a review, or describe a product..."
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

          {/* Right panel — mappings, evidence, etc. */}
          {hasChat && (
            <section className="flex w-[480px] shrink-0 flex-col border-l border-hairline bg-mist">
              {/* Panel tab bar */}
              <div className="flex shrink-0 items-center justify-between border-b border-hairline bg-paper px-4">
                <div className="flex overflow-x-auto">
                  {(
                    [
                      "mappings",
                      "evidence",
                      "coverage",
                      "process",
                      "data",
                      "graph",
                    ] as WorkspaceTab[]
                  ).map((t) => (
                    <button
                      key={t}
                      onClick={() => { setTab(t); setPanelOpen(true); }}
                      className={`relative shrink-0 px-3 py-3.5 text-[12px] font-medium capitalize transition-colors ${
                        tab === t && panelOpen ? "text-signal" : "text-muted hover:text-ink"
                      }`}
                    >
                      {tabLabel(t)}
                      {t === "evidence" && evidence.length > 0 && (
                        <span className="ml-1 rounded-full bg-mist px-1.5 py-0.5 font-mono text-[10px] text-ink">
                          {evidence.length}
                        </span>
                      )}
                      {t === "coverage" && coverageReport && (
                        <span className="ml-1 rounded-full bg-mist px-1.5 py-0.5 font-mono text-[10px] text-ink">
                          {coverageReport.inventory.requirements.filter(
                            (item) => item.kind === "value" && !item.wildcard
                          ).length}
                        </span>
                      )}
                      {t === "graph" && mappingKnowledge.length > 0 && (
                        <span className="ml-1 rounded-full bg-mist px-1.5 py-0.5 font-mono text-[10px] text-ink">
                          {mappingKnowledge.length}
                        </span>
                      )}
                      {t === "data" && artifacts.length > 0 && (
                        <span className="ml-1 rounded-full bg-mist px-1.5 py-0.5 font-mono text-[10px] text-ink">
                          {artifacts.length}
                        </span>
                      )}
                      {tab === t && panelOpen && (
                        <span className="absolute inset-x-2 -bottom-px h-[2px] rounded-t-full bg-signal" />
                      )}
                    </button>
                  ))}
                </div>
                {tab === "mappings" && pending > 0 && panelOpen && (
                  <button
                    onClick={approveAll}
                    className="shrink-0 rounded-full border border-hairline px-3 py-1 text-[11px] font-medium transition-all hover:bg-mist"
                  >
                    Approve all
                  </button>
                )}
              </div>

              {/* Panel content */}
              <div className="scroll-quiet min-h-0 flex-1 overflow-y-auto p-4">
                {tab === "mappings" ? (
                  mappings.length === 0 ? (
                    <Empty
                      title="No mappings yet"
                      body="Send a product description and the proposed mappings will appear here for your approval."
                    />
                  ) : (
                    <div className="space-y-4">
                      <div className="flex flex-wrap gap-2">
                        {mappingResult ? (
                          <>
                            <Stat label="Extracted facts" value={evidence.length} tone="plain" />
                            <Stat label="Mapped auto" value={websiteAutoMapped} tone="ok" />
                            <Stat label="Needs review" value={websiteNeedsReview} tone="warn" />
                            <Stat label="Unmatched" value={mappingResult.unmatchedEvidenceIds.length} tone="plain" />
                          </>
                        ) : (
                          <>
                            <Stat label="Ready" value={ready} tone="ok" />
                            <Stat label="Needs you" value={pending} tone="warn" />
                            <Stat label="Gaps" value={gaps.length} tone="plain" />
                          </>
                        )}
                      </div>

                      {semanticReview.length > 0 && (
                        <div className="rounded-xl border border-signal/20 bg-signal/5 p-4">
                          <p className="text-[13px] font-semibold text-ink">
                            Human semantic review required
                          </p>
                          <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
                            Every retained fact is shown below. Correct only what is wrong; unchanged rows are already set to keep.
                          </p>
                          <button
                            onClick={() => void confirmSemanticReview()}
                            disabled={semanticReview.some((item) => !reviewDecisions[item.id])}
                            className="mt-3 rounded-full bg-ink px-4 py-1.5 text-[12px] font-medium text-white disabled:cursor-not-allowed disabled:opacity-30"
                          >
                            Confirm mappings
                          </button>
                        </div>
                      )}

                      {gaps.length > 0 && (
                        <div className="rounded-xl border border-warn/20 bg-warn/[0.04] p-4">
                          <p className="text-[13px] font-semibold text-warn">Required elements still missing</p>
                          <p className="mt-1.5 font-mono text-[12px] leading-relaxed text-ink/80">
                            {gaps.join(" · ")}
                          </p>
                          <p className="mt-2 text-[12px] text-muted">
                            Add these values in the chat. MIA will not invent them.
                          </p>
                        </div>
                      )}

                      {/* Supplier Outreach */}
                      {gaps.length > 0 && outreachStatus !== "responded" && (
                        <div className="rounded-xl border border-hairline bg-paper p-4">
                          <p className="text-[13px] font-semibold text-ink">Supplier Outreach</p>
                          <p className="mt-1 text-[12px] leading-relaxed text-muted">
                            Send a data-request email to your supplier. MIA auto-fills the passport when they respond.
                          </p>
                          {outreachStatus === "idle" || outreachStatus === "error" ? (
                            <>
                              <div className="mt-3 flex gap-2">
                                <input
                                  type="email"
                                  value={supplierEmail}
                                  onChange={(e) => setSupplierEmail(e.target.value)}
                                  placeholder="supplier@example.com"
                                  className="flex-1 rounded-lg border border-hairline bg-mist px-3 py-2 text-[13px] text-ink placeholder:text-muted/60 focus:border-signal/50 focus:outline-none focus:ring-2 focus:ring-signal/10"
                                />
                                <button
                                  onClick={() => void sendGapEmail()}
                                  disabled={!supplierEmail || gaps.length === 0}
                                  className="rounded-full bg-ink px-4 py-2 text-[12px] font-medium text-white disabled:opacity-30"
                                >
                                  Send
                                </button>
                              </div>
                              {outreachStatus === "error" && (
                                <p className="mt-2 text-[11px] text-warn">{outreachError}</p>
                              )}
                            </>
                          ) : outreachStatus === "sending" ? (
                            <p className="mt-3 text-[12px] text-muted">Sending...</p>
                          ) : (
                            <div className="mt-3 flex items-center gap-2">
                              <span className="h-2 w-2 animate-pulse rounded-full bg-ok" />
                              <p className="text-[12px] text-muted">
                                Email sent to <strong className="text-ink">{supplierEmail}</strong>. Polling every 10s...
                              </p>
                            </div>
                          )}
                        </div>
                      )}

                      {gaps.length > 0 && outreachStatus === "responded" && (
                        <div className="rounded-xl border border-ok/20 bg-ok/[0.04] p-4">
                          <p className="text-[13px] font-semibold text-ok">Supplier responded</p>
                          <p className="mt-1 text-[12px] text-muted">
                            Missing fields received from <strong className="text-ink">{supplierEmail}</strong>.
                          </p>
                        </div>
                      )}

                      <div className="space-y-3">
                        {semanticReview.length > 0
                          ? semanticReview.map((item) => {
                              const record = evidence.find((candidate) => candidate.id === item.evidenceId);
                              return record ? (
                                <MappingReviewRow
                                  key={item.id}
                                  item={item}
                                  evidence={record}
                                  targets={correctionTargets}
                                  decision={reviewDecisions[item.id]}
                                  onChange={(decision) =>
                                    setReviewDecisions((previous) => ({ ...previous, [item.id]: decision }))
                                  }
                                />
                              ) : null;
                            })
                          : mappings.map((m) => (
                              <MappingRow
                                key={m.id}
                                mapping={m}
                                elements={correctionTargets}
                                onDecide={decide}
                                onCorrect={correct}
                              />
                            ))}
                      </div>

                      {dpp && <DppView dpp={dpp} />}

                      {dpp && (
                        <div className="rounded-xl border border-hairline bg-paper p-4">
                          {deployStatus !== "deployed" ? (
                            <>
                              <p className="text-[13px] font-semibold text-ink">Deploy to BaSyx</p>
                              <p className="mt-1 text-[12px] leading-relaxed text-muted">
                                Upload your passport to a live AAS server and get a shareable URL and QR code.
                              </p>
                              <button
                                onClick={() => void deployPassport()}
                                disabled={!threadId || deployStatus === "deploying"}
                                className="mt-3 rounded-full bg-ink px-4 py-1.5 text-[12px] font-medium text-white transition-all hover:shadow-md disabled:opacity-30"
                              >
                                {deployStatus === "deploying" ? "Deploying..." : "Deploy Passport"}
                              </button>
                              {deployStatus === "error" && (
                                <p className="mt-2 text-[11px] text-warn">{deployError}</p>
                              )}
                            </>
                          ) : deployResult ? (
                            <>
                              <div className="flex items-center gap-2">
                                <div className="h-2 w-2 rounded-full bg-ok" />
                                <p className="text-[13px] font-semibold text-ink">Passport deployed</p>
                              </div>
                              {deployResult.qr_code_png_b64 && (
                                <div className="mt-4 flex justify-center">
                                  <img
                                    src={`data:image/png;base64,${deployResult.qr_code_png_b64}`}
                                    alt="Passport QR Code"
                                    className="h-48 w-48"
                                    style={{ imageRendering: "pixelated" }}
                                  />
                                </div>
                              )}
                              <p className="mt-3 break-all font-mono text-[11px] text-muted">
                                {deployResult.passport_url}
                              </p>
                              <div className="mt-3 flex flex-wrap gap-2">
                                <button
                                  onClick={() => void navigator.clipboard.writeText(deployResult.passport_url)}
                                  className="rounded-full border border-hairline bg-mist px-3 py-1.5 text-[12px] font-medium text-ink transition-colors hover:bg-paper"
                                >
                                  Copy link
                                </button>
                                <a
                                  href={deployResult.passport_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="rounded-full border border-signal/30 bg-signalDim px-3 py-1.5 text-[12px] font-medium text-signal transition-colors hover:bg-signal/15"
                                >
                                  Open passport
                                </a>
                              </div>
                            </>
                          ) : null}
                        </div>
                      )}
                    </div>
                  )
                ) : tab === "evidence" ? (
                  <EvidencePanel evidence={evidence} mappingResult={mappingResult} />
                ) : tab === "coverage" ? (
                  <CoveragePanel report={coverageReport} evidence={evidence} mappingResult={mappingResult} />
                ) : tab === "process" ? (
                  <AgentActivity events={agentActivity} />
                ) : tab === "data" ? (
                  <WorkspaceExplorer apiUrl={API_URL} threadId={threadId} artifacts={artifacts} />
                ) : (
                  <IntegrationGraph entries={mappingKnowledge} />
                )}
              </div>
            </section>
          )}
        </div>
      </div>
    </>
  );
}

function tabLabel(tab: WorkspaceTab): string {
  if (tab === "graph") return "Graph";
  if (tab === "process") return "Process";
  if (tab === "data") return "Data";
  if (tab === "coverage") return "Coverage";
  if (tab === "evidence") return "Evidence";
  return "Mappings";
}

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
    tone === "ok"
      ? "text-ok"
      : tone === "warn"
      ? "text-warn"
      : "text-muted";
  return (
    <div className="flex flex-col rounded-xl border border-hairline bg-paper px-3 py-2 shadow-sm">
      <span className={`font-mono text-[16px] font-semibold tabular-nums ${cls}`}>
        {value}
      </span>
      <span className="mt-0.5 text-[11px] text-muted">{label}</span>
    </div>
  );
}

function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="mx-auto max-w-xs pt-16 text-center">
      <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-full border border-hairline bg-paper text-muted shadow-sm">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
          <polyline points="10 9 9 9 8 9" />
        </svg>
      </div>
      <p className="text-[14px] font-semibold text-ink">{title}</p>
      <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{body}</p>
    </div>
  );
}
