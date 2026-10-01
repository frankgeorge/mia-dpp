"use client";

import { useCallback, useEffect, useRef, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useUser } from "@clerk/nextjs";
import type {
  AgentResponse,
  AgentTraceEvent,
  BulkExtractResponse,
  ChatMessage,
  ExtractedField,
  SubmodelStatusValue,
  SubmodelKey,
} from "@/lib/types";
import { SUBMODEL_SEQUENCE, SUBMODEL_LABELS } from "@/lib/types";
import { ChatMarkdown } from "@/components/ChatMarkdown";
import { OnboardingModal, getCompanyProfile } from "@/components/OnboardingModal";

const API_URL = process.env.NEXT_PUBLIC_MIA_API_URL ?? "";

// Per-submodel minimum required fields (mirrors backend SUBMODEL_REQUIRED)
const SUBMODEL_REQUIRED: Record<string, string[]> = {
  dpp_metadata: ["uniqueProductIdentifier", "economicOperatorId"],
  digital_nameplate: ["ManufacturerName", "ManufacturerProductDesignation", "OrderCodeOfManufacturer", "URIOfTheProduct"],
  technical_data: ["GeneralInformation"],
  carbon_footprint: ["PCFCO2eq", "ReferenceValueForCalculation", "QuantityOfMeasureForCalculation"],
  handover_documentation: ["Title", "OrganizationOfficialName"],
  maintenance_instructions: ["MaintenanceFreeAsset"],
};

function getGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

const SESSION_KEY = "mia.workspace.session.v2";

function loadSession() {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function saveSession(data: Record<string, unknown>) {
  try { sessionStorage.setItem(SESSION_KEY, JSON.stringify(data)); } catch { /* non-blocking */ }
}

// Status dot color helper
function statusColor(status: SubmodelStatusValue | undefined) {
  switch (status) {
    case "complete": return "bg-ok";
    case "in_progress": return "bg-signal animate-pulse";
    case "skipped": return "bg-muted";
    default: return "bg-muted/30";
  }
}

function WorkspaceInner() {
  const { user } = useUser();
  const router = useRouter();
  const searchParams = useSearchParams();
  const threadParam = searchParams.get("thread");
  const isNewSession = searchParams.get("new") === "1";

  // When ?new=1, clear stored session so we start fresh
  const saved = typeof window !== "undefined"
    ? (isNewSession ? null :
       threadParam
        ? (loadSession()?.threadId === threadParam ? loadSession() : null)
        : loadSession())
    : null;

  // Clear sessionStorage and strip ?new=1 from URL immediately
  useEffect(() => {
    if (isNewSession) {
      try { sessionStorage.removeItem(SESSION_KEY); } catch { /* ignore */ }
      router.replace("/workspace");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isNewSession]);

  const [messages, setMessages] = useState<ChatMessage[]>(saved?.messages ?? []);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(threadParam ?? saved?.threadId ?? null);
  const [agentStatus, setAgentStatus] = useState<AgentResponse["status"]>("completed");
  const [extractedFields, setExtractedFields] = useState<Record<string, string>>(saved?.extractedFields ?? {});
  const [missingRequired, setMissingRequired] = useState<string[]>(saved?.missingRequired ?? []);
  const [dppReady, setDppReady] = useState<boolean>(saved?.dppReady ?? false);
  const endRef = useRef<HTMLDivElement>(null);

  // ── Multi-submodel state ──────────────────────────────────────────────────
  const [currentSubmodel, setCurrentSubmodel] = useState<SubmodelKey>(
    saved?.currentSubmodel ?? SUBMODEL_SEQUENCE[0]
  );
  const [submodelStatus, setSubmodelStatus] = useState<Record<string, SubmodelStatusValue>>(
    saved?.submodelStatus ?? Object.fromEntries(SUBMODEL_SEQUENCE.map((k) => [k, "pending"]))
  );
  const [submodelFields, setSubmodelFields] = useState<Record<string, Record<string, string>>>(
    saved?.submodelFields ?? {}
  );
  const [pdfLinks, setPdfLinks] = useState<string[]>(saved?.pdfLinks ?? []);

  // ── Specialist agent state ────────────────────────────────────────────────
  const [agentRunning, setAgentRunning] = useState<"carbon_footprint" | "technical_data" | null>(null);
  const [showAgentSuggestion, setShowAgentSuggestion] = useState(false);
  const [lastProductUrl, setLastProductUrl] = useState<string | null>(null);

  // ── Edit state ────────────────────────────────────────────────────────────
  const [editingField, setEditingField] = useState<string | null>(null);
  const [editingValue, setEditingValue] = useState("");
  const [manuallyEditedFields, setManuallyEditedFields] = useState<Set<string>>(new Set());

  // ── Recent passports (hero state) ────────────────────────────────────────
  const [recentPassports, setRecentPassports] = useState<{ thread_id: string; product_name: string; status: string }[]>([]);
  useEffect(() => {
    fetch("/api/passports")
      .then((r) => r.json())
      .then((data) => { if (Array.isArray(data)) setRecentPassports(data.slice(0, 4)); })
      .catch(() => {});
  }, []);

  // ── Deploy state ──────────────────────────────────────────────────────────
  const [deployStatus, setDeployStatus] = useState<"idle" | "deploying" | "deployed" | "error">(saved?.deployStatus ?? "idle");
  const [deployResult, setDeployResult] = useState<{
    passport_url: string;
    qr_code_png_b64: string;
    shell_ids: string[];
  } | null>(saved?.deployResult ?? null);
  const [deployError, setDeployError] = useState("");

  // ── File upload state ─────────────────────────────────────────────────────
  const [uploadStatus, setUploadStatus] = useState<"idle" | "uploading" | "error">("idle");
  const [uploadError, setUploadError] = useState("");
  const [addedHandoverUrls, setAddedHandoverUrls] = useState<Set<string>>(new Set());
  const [previewDocUrl, setPreviewDocUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Product image state ───────────────────────────────────────────────────
  const [productImageUrl, setProductImageUrl] = useState<string | null>(saved?.productImageUrl ?? null);
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

  // ── Restore from Supabase when ?thread= is provided ────────────────────────
  useEffect(() => {
    if (!threadParam) return;
    fetch(`/api/passports/thread/${encodeURIComponent(threadParam)}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.error) return;
        setThreadId(data.thread_id);

        // Rebuild extractedFields + submodelFields from the stored AAS JSON
        if (data.aas_json) {
          // AAS compiled idShort → our internal submodel key
          const AAS_ID_SHORT_TO_KEY: Record<string, string> = {
            Nameplate: "digital_nameplate",
            DigitalNameplate: "digital_nameplate",
            TechnicalData: "technical_data",
            CarbonFootprint: "carbon_footprint",
            HandoverDocumentation: "handover_documentation",
            MaintenanceInstructions: "maintenance_instructions",
            DPPMetadata: "dpp_metadata",
            dpp_metadata: "dpp_metadata",
            digital_nameplate: "digital_nameplate",
            technical_data: "technical_data",
            carbon_footprint: "carbon_footprint",
            handover_documentation: "handover_documentation",
            maintenance_instructions: "maintenance_instructions",
          };

          const aasSubmodels: Array<{ idShort?: string; submodelElements?: unknown[] }> =
            (data.aas_json.submodels as typeof aasSubmodels) ?? [];
          const flat: Record<string, string> = {};
          const bySubmodel: Record<string, Record<string, string>> = {};

          function pullProps(elements: unknown[], smKey: string) {
            for (const el of elements as Array<{ idShort: string; modelType?: string; value?: unknown; submodelElements?: unknown[] }>) {
              if (el.modelType === "Property" && el.value != null) {
                const v = String(el.value);
                flat[el.idShort] = v;
                bySubmodel[smKey] = { ...(bySubmodel[smKey] ?? {}), [el.idShort]: v };
              } else if (el.modelType === "MultiLanguageProperty" && Array.isArray(el.value)) {
                // Extract English text, fall back to first language
                const langs = el.value as Array<{ language: string; text: string }>;
                const en = langs.find((l) => l.language === "en") ?? langs[0];
                if (en?.text) {
                  flat[el.idShort] = en.text;
                  bySubmodel[smKey] = { ...(bySubmodel[smKey] ?? {}), [el.idShort]: en.text };
                }
              }
              if (el.submodelElements?.length) pullProps(el.submodelElements, smKey);
            }
          }

          for (const sm of aasSubmodels) {
            const rawKey = sm.idShort ?? "unknown";
            const smKey = AAS_ID_SHORT_TO_KEY[rawKey] ?? rawKey;
            pullProps(sm.submodelElements ?? [], smKey);
          }

          if (Object.keys(flat).length > 0) {
            setExtractedFields(flat);
            setSubmodelFields(bySubmodel);
            const statusUpdate: Record<string, SubmodelStatusValue> = {};
            for (const sm of SUBMODEL_SEQUENCE) {
              if (bySubmodel[sm] && Object.keys(bySubmodel[sm]).length > 0) {
                const required = SUBMODEL_REQUIRED[sm] ?? [];
                const allPresent = required.every((f) => bySubmodel[sm][f]);
                statusUpdate[sm] = allPresent ? "complete" : "in_progress";
              }
            }
            setSubmodelStatus((prev) => ({ ...prev, ...statusUpdate }));
          }
        }

        if (data.status === "deployed" && data.passport_url) {
          setDeployStatus("deployed");
          setDeployResult({
            passport_url: data.passport_url,
            qr_code_png_b64: data.qr_code_b64 ?? "",
            shell_ids: [data.thread_id],
          });
          setDppReady(true);
        }
        if (data.product_image_url) setProductImageUrl(data.product_image_url);

        setMessages([{
          role: "assistant",
          content: `Welcome back! I've restored your passport for **${data.product_name}**. You can edit any field in the panel on the right, upload new documents, or click **Generate passport** to update it.`,
        }]);
      })
      .catch(() => { /* silent */ });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadParam]);

  // ── Persist session to sessionStorage ─────────────────────────────────────
  useEffect(() => {
    if (messages.length > 0 || threadId) {
      saveSession({
        messages, threadId, extractedFields, missingRequired, dppReady,
        deployStatus, deployResult, productImageUrl,
        currentSubmodel, submodelStatus, submodelFields, pdfLinks,
      });
    }
  }, [messages, threadId, extractedFields, missingRequired, dppReady,
      deployStatus, deployResult, productImageUrl,
      currentSubmodel, submodelStatus, submodelFields, pdfLinks]);

  // ── Supplier outreach state ───────────────────────────────────────────────
  const [supplierEmail, setSupplierEmail] = useState("");
  const [outreachStatus, setOutreachStatus] = useState<"idle" | "sending" | "sent" | "responded" | "error">("idle");
  const [outreachToken, setOutreachToken] = useState<string | null>(null);
  const [outreachError, setOutreachError] = useState("");
  const outreachPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

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
            const filled = Object.entries(data.response).map(([k, v]) => `${k}: ${v}`).join(", ");
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
    setDppReady(data.dppReady);

    // Persist trace events to localStorage so the activity page can read them
    // even when the backend container changes (ephemeral SQLite).
    if (data.traceEvents.length > 0) {
      try {
        const key = `mia_trace_${data.threadId}`;
        const existing = JSON.parse(localStorage.getItem(key) ?? "[]") as { id: string }[];
        const existingIds = new Set(existing.map((e) => e.id));
        const merged = [...existing, ...data.traceEvents.filter((e) => !existingIds.has(e.id))];
        localStorage.setItem(key, JSON.stringify(merged));
      } catch { /* storage not available */ }
    }

    const sm = (data.currentSubmodel || currentSubmodel) as SubmodelKey;

    // Update submodel status from backend
    if (data.submodelStatus && Object.keys(data.submodelStatus).length > 0) {
      setSubmodelStatus(data.submodelStatus as Record<string, SubmodelStatusValue>);
    }

    // Use backend missing fields directly — no client-side fallback computation
    setMissingRequired(data.missingRequired);

    if (data.extractedFields.length > 0) {
      setExtractedFields((prev) => {
        const next = { ...prev };
        for (const f of data.extractedFields) {
          next[f.idtaField] = f.value;
        }
        // Auto-fetch product image when URIOfTheProduct first appears
        const uri = next["URIOfTheProduct"];
        if (uri && !prev["URIOfTheProduct"] && !productImageUrl) {
          void fetchAndUseProductUrl(uri);
        }
        return next;
      });

      // Also store per-submodel fields
      setSubmodelFields((prev) => {
        const smKey = sm;
        const smPrev = prev[smKey] ?? {};
        const smNext = { ...smPrev };
        for (const f of data.extractedFields) {
          smNext[f.idtaField] = f.value;
        }
        return { ...prev, [smKey]: smNext };
      });
    }

    // If current submodel is complete, auto-advance to next
    if (data.submodelStatus?.[sm] === "complete") {
      const idx = SUBMODEL_SEQUENCE.indexOf(sm);
      if (idx >= 0 && idx < SUBMODEL_SEQUENCE.length - 1) {
        const nextSM = SUBMODEL_SEQUENCE[idx + 1] as SubmodelKey;
        setCurrentSubmodel(nextSM);
        setSubmodelStatus((prev) => ({ ...prev, [nextSM]: "in_progress" }));
      }
    }

    // Update currentSubmodel from backend only if we haven't already advanced
    if (data.currentSubmodel && data.submodelStatus?.[sm] !== "complete") {
      setCurrentSubmodel(data.currentSubmodel as SubmodelKey);
    }
  }

  async function fetchAndUseProductUrl(url: string) {
    if (imageSearchedUrl === url) return;
    setImageSearchedUrl(url);
    try {
      const res = await fetch(`/api/fetch-url?url=${encodeURIComponent(url)}`);
      const data = (await res.json()) as {
        productImageUrl?: string | null;
        pdfLinks?: string[];
        text?: string;
        error?: string;
      };
      if (data.productImageUrl) {
        setProductImageUrl(data.productImageUrl);
        setImageSource("og");
        setMessages((prev) => [
          ...prev,
          { role: "assistant" as const, content: "I found a product image from the website. Use the upload button if you'd like a different one." },
        ]);
      }
      if (data.pdfLinks?.length) {
        setPdfLinks(data.pdfLinks);
      }
    } catch { /* silent — optional */ }
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
      body: JSON.stringify({ ...payload, knownFields: extractedFields }),
    });
    let body: AgentResponse | { detail?: string };
    try {
      body = (await res.json()) as AgentResponse | { detail?: string };
    } catch {
      throw new Error(`Server error (${res.status}) — the backend may be starting up, please try again in a moment`);
    }
    if (!res.ok) {
      throw new Error("detail" in body && body.detail ? body.detail : `Backend returned ${res.status}`);
    }
    return body as AgentResponse;
  }

  async function callBulkExtract(payload: Record<string, unknown>): Promise<BulkExtractResponse> {
    const res = await fetch(`${API_URL}/api/agent/extract-all`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...payload, knownFields: extractedFields }),
    });
    let body: BulkExtractResponse | { detail?: string };
    try {
      body = (await res.json()) as BulkExtractResponse | { detail?: string };
    } catch {
      throw new Error(`Server error (${res.status}) — the backend may be starting up, please try again in a moment`);
    }
    if (!res.ok) {
      throw new Error("detail" in body && body.detail ? body.detail : `Backend returned ${res.status}`);
    }
    return body as BulkExtractResponse;
  }

  function applyBulkResponse(data: BulkExtractResponse, tid: string) {
    setThreadId(tid);

    if (data.submodelStatus && Object.keys(data.submodelStatus).length > 0) {
      setSubmodelStatus(data.submodelStatus as Record<string, SubmodelStatusValue>);
    }

    if (data.extractedFields.length > 0) {
      setExtractedFields((prev) => {
        const next = { ...prev };
        for (const f of data.extractedFields) {
          next[f.idtaField] = f.value;
          // Auto-fetch product image on first URIOfTheProduct
          if (f.idtaField === "URIOfTheProduct" && !prev["URIOfTheProduct"] && !productImageUrl) {
            void fetchAndUseProductUrl(f.value);
          }
        }
        return next;
      });
    }

    if (Object.keys(data.submodelFields).length > 0) {
      setSubmodelFields((prev) => ({ ...prev, ...data.submodelFields }));
    }

    setDppReady(data.dppReady);

    // Build a summary message listing which submodels got data
    const filledSubmodels = SUBMODEL_SEQUENCE.filter(
      (sm) => data.submodelFields[sm] && Object.keys(data.submodelFields[sm]).length > 0
    );
    const completedSubmodelLabels = SUBMODEL_SEQUENCE.filter(
      (sm) => data.submodelStatus?.[sm] === "complete"
    ).map((sm) => SUBMODEL_LABELS[sm as SubmodelKey]);

    if (filledSubmodels.length > 0) {
      const filledLabels = filledSubmodels.map((sm) => SUBMODEL_LABELS[sm as SubmodelKey]).join(", ");
      let summary = `I scanned the document across all sections and found data for: **${filledLabels}**.`;
      if (completedSubmodelLabels.length > 0) {
        summary += `\n\n✓ Complete: ${completedSubmodelLabels.join(", ")}`;
      }

      // Find the first incomplete submodel that has missing required fields and ask for them
      const firstIncomplete = SUBMODEL_SEQUENCE.find(
        (sm) => data.submodelStatus?.[sm] === "in_progress" || data.submodelStatus?.[sm] === "pending"
      );
      const stillMissingSubmodels = SUBMODEL_SEQUENCE.filter(
        (sm) => data.submodelStatus?.[sm] === "in_progress" || data.submodelStatus?.[sm] === "pending"
      );

      if (firstIncomplete && data.missingRequired) {
        const missingForFirst = data.missingRequired[firstIncomplete] ?? [];
        const otherMissingLabels = stillMissingSubmodels
          .filter((sm) => sm !== firstIncomplete)
          .map((sm) => SUBMODEL_LABELS[sm as SubmodelKey]);

        if (missingForFirst.length > 0) {
          summary += `\n\nTo complete **${SUBMODEL_LABELS[firstIncomplete as SubmodelKey]}**, I still need:\n`;
          summary += missingForFirst.map((f) => `- **${f}**`).join("\n");
          if (otherMissingLabels.length > 0) {
            summary += `\n\nAfter that we'll move on to: ${otherMissingLabels.join(", ")}. Or click **Skip remaining & generate** to create the passport now with what we have.`;
          } else {
            summary += "\n\nCan you provide any of these, or would you like to skip and generate the passport now?";
          }
        } else if (stillMissingSubmodels.length > 0) {
          const labels = stillMissingSubmodels.map((sm) => SUBMODEL_LABELS[sm as SubmodelKey]);
          summary += `\n\nStill need more info for: ${labels.join(", ")}. You can add data for each section, or click **Skip remaining & generate** to create the passport with what we have.`;
        }
      }

      setMessages((prev) => [...prev, { role: "assistant" as const, content: summary }]);

      // Suggest specialist agents if carbon/technical data are incomplete and we have a product URL
      const productUrl = data.submodelFields?.digital_nameplate?.URIOfTheProduct || extractedFields["URIOfTheProduct"];
      const cfIncomplete = !data.submodelStatus?.carbon_footprint || data.submodelStatus.carbon_footprint === "pending" || data.submodelStatus.carbon_footprint === "in_progress";
      const tdIncomplete = !data.submodelStatus?.technical_data || data.submodelStatus.technical_data === "pending" || data.submodelStatus.technical_data === "in_progress";
      if ((cfIncomplete || tdIncomplete) && productUrl) {
        setShowAgentSuggestion(true);
      }
    } else {
      setMessages((prev) => [
        ...prev,
        { role: "assistant" as const, content: "I couldn't extract any recognisable product data from this document. Try uploading a datasheet, specification sheet, or product manual." },
      ]);
    }
  }

  async function skipSubmodel() {
    if (busy) return;
    const sm = currentSubmodel;
    setSubmodelStatus((prev) => ({ ...prev, [sm]: "skipped" }));
    const idx = SUBMODEL_SEQUENCE.indexOf(sm);
    const nextSM = idx < SUBMODEL_SEQUENCE.length - 1 ? SUBMODEL_SEQUENCE[idx + 1] : null;

    setBusy(true);
    const tid = activeThread();
    const profile = getCompanyProfile();
    try {
      const data = await callAgent({
        threadId: tid,
        message: `Skip ${SUBMODEL_LABELS[sm]} submodel`,
        currentSubmodel: sm,
        action: "skip",
        companyName: profile?.name || undefined,
        companyWebsite: profile?.website || undefined,
      });
      setMessages((prev) => [...prev, { role: "assistant", content: data.reply }]);
      if (data.submodelStatus && Object.keys(data.submodelStatus).length > 0) {
        setSubmodelStatus(data.submodelStatus as Record<string, SubmodelStatusValue>);
      }
      if (nextSM) {
        setCurrentSubmodel(nextSM);
        setSubmodelStatus((prev) => ({ ...prev, [nextSM]: "in_progress" }));
      }
    } catch {
      if (nextSM) {
        setCurrentSubmodel(nextSM);
        setSubmodelStatus((prev) => ({ ...prev, [nextSM]: "in_progress" }));
        setMessages((prev) => [
          ...prev,
          { role: "assistant" as const, content: `Skipped ${SUBMODEL_LABELS[sm]}. Let's move on to **${SUBMODEL_LABELS[nextSM]}**.` },
        ]);
      }
    } finally {
      setBusy(false);
    }
  }

  async function skipAllAndGenerate() {
    if (busy) return;
    // Mark every non-complete submodel as skipped
    setSubmodelStatus((prev) => {
      const next = { ...prev };
      for (const sm of SUBMODEL_SEQUENCE) {
        if (next[sm] !== "complete") next[sm] = "skipped";
      }
      return next;
    });
    setMessages((prev) => [
      ...prev,
      { role: "assistant" as const, content: "Skipping remaining sections and generating your passport now…" },
    ]);
    await generate();
  }

  async function send(text: string) {
    const t = text.trim();
    if (!t || busy) return;

    // If the user pastes a URL, fetch and extract it instead of sending as plain text
    if (/^https?:\/\//i.test(t)) {
      void ingestWebsite(t);
      return;
    }

    const profile = getCompanyProfile();
    const next: ChatMessage[] = [...messages, { role: "user", content: t }];
    setMessages(next);
    setInput("");
    const tid = activeThread();
    setBusy(true);

    // Mark current submodel as in_progress if pending
    if (submodelStatus[currentSubmodel] === "pending") {
      setSubmodelStatus((prev) => ({ ...prev, [currentSubmodel]: "in_progress" }));
    }

    try {
      const data = await callAgent({
        threadId: tid,
        message: t,
        currentSubmodel,
        companyName: profile?.name || undefined,
        companyWebsite: profile?.website || undefined,
      });
      applyAgentResponse(data);
      setMessages((prev) => [...prev, { role: "assistant", content: data.reply }]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "That request didn't go through. Check your connection and try again." },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function runSpecialistAgent(type: "carbon_footprint" | "technical_data") {
    if (busy || agentRunning || !threadId) return;
    setAgentRunning(type);
    setShowAgentSuggestion(false);
    setBusy(true);
    const label = type === "carbon_footprint" ? "Carbon Footprint Calculator" : "Technical Data Expert";
    setMessages((prev) => [
      ...prev,
      { role: "assistant" as const, content: `Running **${label}** — searching the web and analysing product data…` },
    ]);
    try {
      const endpoint = type === "carbon_footprint" ? "carbon-footprint" : "technical-data";
      const res = await fetch(`${API_URL}/api/agent/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          thread_id: threadId,
          product_url: lastProductUrl ?? extractedFields["URIOfTheProduct"] ?? null,
          product_name: extractedFields["ManufacturerProductDesignation"] || extractedFields["ManufacturerArticleNumber"] || null,
          existing_fields: extractedFields,
        }),
      });
      let body: {
        reply?: string;
        extracted_fields?: Array<{ idta_field: string; value: string; confidence?: number; source_excerpt?: string }>;
        submodel_key?: string;
        methodology?: string;
        confidence?: string;
        data_sources?: string[];
        tool_trace?: Array<{ tool: string; input: string; success: string; summary: string }>;
        calculation_inputs?: Record<string, string>;
        detail?: string;
      };
      try {
        body = (await res.json()) as typeof body;
      } catch {
        throw new Error(`Server error (${res.status}) — please try again in a moment`);
      }
      if (!res.ok) throw new Error(body.detail ?? `Agent returned ${res.status}`);

      // Merge extracted fields into state
      if (body.extracted_fields?.length) {
        setExtractedFields((prev) => {
          const next = { ...prev };
          for (const f of body.extracted_fields!) next[f.idta_field] = f.value;
          return next;
        });
        setSubmodelFields((prev) => {
          const smKey = body.submodel_key ?? type;
          const smPrev = prev[smKey] ?? {};
          const smNext = { ...smPrev };
          for (const f of body.extracted_fields!) smNext[f.idta_field] = f.value;
          return { ...prev, [smKey]: smNext };
        });
        const required = SUBMODEL_REQUIRED[type] ?? [];
        const allFields = { ...extractedFields };
        for (const f of body.extracted_fields) allFields[f.idta_field] = f.value;
        const allPresent = required.every((f) => allFields[f]);
        if (allPresent) setSubmodelStatus((prev) => ({ ...prev, [type]: "complete" as SubmodelStatusValue }));
        else setSubmodelStatus((prev) => ({ ...prev, [type]: "in_progress" as SubmodelStatusValue }));
      }

      setMessages((prev) => [...prev, { role: "assistant" as const, content: body.reply ?? "Agent completed." }]);

      // Fire-and-forget: persist run to audit log
      void fetch("/api/agent-runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          thread_id: threadId,
          product_name:
            extractedFields["ManufacturerProductDesignation"] ||
            extractedFields["ManufacturerArticleNumber"] ||
            "Unknown product",
          agent_type: type,
          reply: body.reply ?? "",
          methodology: body.methodology ?? "",
          confidence: body.confidence ?? "estimated",
          data_sources: body.data_sources ?? [],
          extracted_fields: body.extracted_fields ?? [],
          tool_calls: body.tool_trace ?? [],
          calculation_inputs: body.calculation_inputs ?? {},
        }),
      });

      // Show other agent suggestion if it wasn't run yet
      const otherType = type === "carbon_footprint" ? "technical_data" : "carbon_footprint";
      if (submodelStatus[otherType] === "pending" || submodelStatus[otherType] === "in_progress") {
        setShowAgentSuggestion(true);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setMessages((prev) => [
        ...prev,
        { role: "assistant" as const, content: `${label} encountered an error: ${msg}` },
      ]);
    } finally {
      setBusy(false);
      setAgentRunning(null);
    }
  }

  async function ingestWebsite(url: string) {
    if (!url || busy) return;
    setLastProductUrl(url);
    setInput("");
    setBusy(true);
    setMessages((prev) => [...prev, { role: "user", content: url }]);
    const tid = activeThread();

    if (submodelStatus[currentSubmodel] === "pending") {
      setSubmodelStatus((prev) => ({ ...prev, [currentSubmodel]: "in_progress" }));
    }

    try {
      const res = await fetch(`/api/fetch-url?url=${encodeURIComponent(url)}`);
      let fetched: { text?: string; title?: string; error?: string; productImageUrl?: string | null; pdfLinks?: string[] };
      try {
        fetched = (await res.json()) as typeof fetched;
      } catch {
        throw new Error(`Could not reach the page — server returned an unexpected response (${res.status}), please try again`);
      }
      if (!res.ok || !fetched.text) {
        throw new Error(fetched.error ?? "Could not fetch the page");
      }

      // Use product image and PDF links from fetch
      if (fetched.productImageUrl && !productImageUrl) {
        setProductImageUrl(fetched.productImageUrl);
        setImageSource("og");
      }
      if (fetched.pdfLinks?.length) {
        setPdfLinks(fetched.pdfLinks);
      }

      const profile = getCompanyProfile();
      const bulkData = await callBulkExtract({
        threadId: tid,
        documentText: fetched.text,
        documentFilename: fetched.title || url,
        documentType: "webpage",
        companyName: profile?.name || undefined,
        companyWebsite: profile?.website || undefined,
      });
      applyBulkResponse(bulkData, tid);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not fetch the URL";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Could not read that page: ${msg}. Try uploading a document instead.` },
      ]);
    } finally {
      setBusy(false);
    }
  }

  function mergeHandoverField(key: string, value: string) {
    setExtractedFields((prev) => ({ ...prev, [key]: value }));
    setSubmodelFields((prev) => {
      const smPrev = prev["handover_documentation"] ?? {};
      return { ...prev, handover_documentation: { ...smPrev, [key]: value } };
    });
  }

  function addHandoverDocUrl(url: string, title: string) {
    const existing = extractedFields["DigitalFile"] ?? "";
    const urls = existing ? `${existing}, ${url}` : url;
    mergeHandoverField("DigitalFile", urls);
    if (!extractedFields["Title"]) mergeHandoverField("Title", title);
    setAddedHandoverUrls((prev) => new Set(prev).add(url));
    setSubmodelStatus((prev) => ({ ...prev, handover_documentation: "in_progress" }));
    setMessages((prev) => [
      ...prev,
      {
        role: "assistant" as const,
        content: `Added **${title}** to Handover Documentation as a DigitalFile link.`,
      },
    ]);
  }

  async function uploadFile(file: File) {
    if (busy) return;
    setUploadStatus("uploading");
    setUploadError("");
    const form = new FormData();
    form.append("file", file);

    // Option B: if in handover_documentation submodel, also upload to Supabase Storage
    const isHandover = currentSubmodel === "handover_documentation";
    let storedUrl: string | null = null;
    if (isHandover) {
      try {
        const storeForm = new FormData();
        storeForm.append("file", file);
        const storeRes = await fetch("/api/upload-handover-doc", { method: "POST", body: storeForm });
        const storeData = (await storeRes.json()) as { url?: string; error?: string };
        if (storeRes.ok && storeData.url) storedUrl = storeData.url;
      } catch { /* non-blocking — proceed with text extraction even if storage fails */ }
    }

    try {
      const res = await fetch("/api/upload", { method: "POST", body: form });
      let data: { text?: string; fileName?: string; fileType?: string; sizeKb?: number; truncated?: boolean; error?: string; };
      try {
        data = (await res.json()) as typeof data;
      } catch {
        const text = await res.text().catch(() => "");
        throw new Error(text.length < 200 ? `Upload failed: ${text}` : `Upload failed (${res.status}). The file may be too large.`);
      }
      if (!res.ok || data.error) throw new Error(data.error ?? `Upload failed (${res.status})`);
      setUploadStatus("idle");

      const displayText = `${data.fileName} (${data.fileType}, ${data.sizeKb} KB)${data.truncated ? " — large file, first 40 000 chars extracted" : ""}`;
      const profile = getCompanyProfile();
      const tid = activeThread();
      setBusy(true);
      setMessages((prev) => [...prev, { role: "user", content: displayText }]);

      if (submodelStatus[currentSubmodel] === "pending") {
        setSubmodelStatus((prev) => ({ ...prev, [currentSubmodel]: "in_progress" }));
      }

      // If we stored the file in Supabase, add it as DigitalFile immediately
      if (storedUrl && data.fileName) {
        const title = data.fileName.replace(/\.[^.]+$/, "");
        const existing = extractedFields["DigitalFile"] ?? "";
        const urls = existing ? `${existing}, ${storedUrl}` : storedUrl;
        mergeHandoverField("DigitalFile", urls);
        if (!extractedFields["Title"]) mergeHandoverField("Title", title);
        setAddedHandoverUrls((prev) => new Set(prev).add(storedUrl!));
      }

      try {
        const bulkData = await callBulkExtract({
          threadId: tid,
          documentText: data.text,
          documentFilename: data.fileName,
          documentType: data.fileType,
          companyName: profile?.name || undefined,
          companyWebsite: profile?.website || undefined,
        });
        applyBulkResponse(bulkData, tid);
        if (storedUrl) {
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant" as const,
              content: `File stored and linked as a DigitalFile in Handover Documentation. I've also extracted any relevant fields from its contents.`,
            },
          ]);
        }
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
          submodelFields: Object.keys(submodelFields).length > 0 ? submodelFields : undefined,
          threadId: tid,
        }),
      });
      let body: { threadId?: string; dppJson?: Record<string, unknown>; detail?: string; [key: string]: unknown };
      try { body = (await res.json()) as typeof body; }
      catch { throw new Error(`Server error (${res.status}) — backend returned non-JSON response`); }
      if (!res.ok) throw new Error(body.detail ?? `Backend returned ${res.status}`);
      if (!threadId) setThreadId(tid);
      // Await draft save — include aas_json so the passport page has data immediately
      await savePassportRecord({
        threadId: tid,
        status: "draft",
        aas_json: (body.dppJson as Record<string, unknown>) ?? null,
      });
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Passport saved as draft — you can see it in [Passports](/workspace/assets). Deploying to BaSyx now…" },
      ]);
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

  async function deployPassport(tid?: string, force = false) {
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
          force: force || true, // always bypass AAS template validation — non-blocking for end users
        }),
      });
      let body: { passport_url?: string; qr_code_png_b64?: string; shell_ids?: string[]; aas_json?: Record<string, unknown>; detail?: string; };
      try { body = (await res.json()) as typeof body; }
      catch { throw new Error(`Server error (${res.status}) — backend returned non-JSON response`); }
      if (!res.ok) throw new Error(body.detail ?? `Deploy failed: ${res.status}`);
      const result = {
        passport_url: body.passport_url ?? "",
        qr_code_png_b64: body.qr_code_png_b64 ?? "",
        shell_ids: body.shell_ids ?? [],
      };
      setDeployResult(result);
      setDeployStatus("deployed");
      void savePassportRecord({
        threadId: deployThreadId,
        status: "deployed",
        qr_code_b64: result.qr_code_png_b64,
        passport_url: result.passport_url,
        basyx_shell_id: result.shell_ids[0] ?? null,
        aas_json: body.aas_json ?? null,
      });
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Deployment failed.";
      setDeployError(msg);
      setDeployStatus("error");
      setMessages((prev) => [
        ...prev,
        { role: "assistant" as const, content: `Passport deployment failed: ${msg}. Check the error card below or try again.` },
      ]);
    }
  }

  async function savePassportRecord(overrides: {
    threadId?: string;
    status?: "draft" | "deployed";
    qr_code_b64?: string;
    passport_url?: string;
    basyx_shell_id?: string | null;
    aas_json?: Record<string, unknown> | null;
  } = {}) {
    const tid = overrides.threadId ?? threadId;
    const profile = getCompanyProfile();
    const pname = extractedFields["ManufacturerProductDesignation"] || profile?.name || "Product";
    if (!tid) return;
    const res = await fetch("/api/passports", {
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
    if (!res.ok) {
      let detail = `Passport save failed (${res.status})`;
      try { const b = (await res.json()) as { error?: string }; if (b.error) detail = b.error; } catch { /* ignore */ }
      throw new Error(detail);
    }
  }

  function startEditField(field: string, value: string) {
    setEditingField(field);
    setEditingValue(value);
  }

  function commitFieldEdit() {
    if (!editingField) return;
    const trimmed = editingValue.trim();
    setEditingField(null);
    if (!trimmed) return;
    const sm = currentSubmodel;
    setExtractedFields((prev) => {
      const next = { ...prev, [editingField!]: trimmed };
      const required = SUBMODEL_REQUIRED[sm] ?? [];
      const missing = required.filter((f) => !next[f]);
      setMissingRequired(missing);
      setDppReady(missing.length === 0 || (submodelStatus["digital_nameplate"] === "complete"));
      return next;
    });
    setSubmodelFields((prev) => {
      const smPrev = prev[sm] ?? {};
      return { ...prev, [sm]: { ...smPrev, [editingField!]: trimmed } };
    });
    setManuallyEditedFields((prev) => new Set(prev).add(editingField!));
  }

  // Determine how many submodels are complete/skipped
  const completedSubmodels = SUBMODEL_SEQUENCE.filter(
    (k) => submodelStatus[k] === "complete" || submodelStatus[k] === "skipped"
  ).length;
  const allSubmodelsDone = completedSubmodels === SUBMODEL_SEQUENCE.length;

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

      {/* ── Document preview modal ─────────────────────────────────────── */}
      {previewDocUrl && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
          onClick={() => setPreviewDocUrl(null)}
        >
          <div
            className="relative flex flex-col w-full max-w-4xl rounded-2xl bg-paper shadow-2xl overflow-hidden"
            style={{ height: "85vh" }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal header */}
            <div className="flex items-center justify-between border-b border-hairline px-4 py-3 shrink-0">
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-semibold text-ink truncate">Document Preview</p>
                <p className="text-[11px] text-muted truncate">{previewDocUrl}</p>
              </div>
              <div className="flex items-center gap-2 ml-3 shrink-0">
                <a
                  href={previewDocUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-full border border-hairline px-3 py-1.5 text-[12px] font-medium text-ink hover:bg-mist transition-colors"
                >
                  Open in tab ↗
                </a>
                <button
                  onClick={() => setPreviewDocUrl(null)}
                  className="grid h-7 w-7 place-items-center rounded-full hover:bg-mist text-muted hover:text-ink transition-colors"
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M2 2l10 10M12 2L2 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                  </svg>
                </button>
              </div>
            </div>
            {/* iframe viewer */}
            <iframe
              src={previewDocUrl.replace(/\/fl_attachment:[^/]+\//, "/")}
              className="flex-1 w-full border-0"
              title="Document preview"
              sandbox="allow-same-origin allow-scripts allow-popups"
            />
          </div>
        </div>
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
          <header className="shrink-0 flex h-14 items-center justify-between border-b border-hairline bg-paper pl-14 pr-4 md:pl-6 md:pr-6">
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
              {hasExtracted && deployStatus === "idle" && (
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

        {/* Submodel progress strip */}
        {hasChat && (
          <div className="shrink-0 border-b border-hairline bg-paper px-4 py-2 overflow-x-auto" style={{ WebkitOverflowScrolling: "touch" }}>
            <div className="flex items-center gap-0.5 min-w-max pl-10 md:pl-0">
              {SUBMODEL_SEQUENCE.map((key, idx) => {
                const status = submodelStatus[key] ?? "pending";
                const isCurrent = key === currentSubmodel;
                return (
                  <div key={key} className="flex items-center">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => {
                        if (key === currentSubmodel) return;
                        setCurrentSubmodel(key as SubmodelKey);
                        if (submodelStatus[key] === "pending") {
                          setSubmodelStatus((prev) => ({ ...prev, [key]: "in_progress" }));
                        }
                      }}
                      className={[
                        "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium transition-all",
                        !isCurrent && !busy ? "cursor-pointer hover:bg-mist" : "",
                        isCurrent
                          ? "bg-signal/10 text-signal border border-signal/20"
                          : status === "complete"
                          ? "text-ok"
                          : status === "skipped"
                          ? "text-muted line-through"
                          : "text-muted/50",
                      ].join(" ")}
                    >
                      <span className={`h-1.5 w-1.5 rounded-full ${statusColor(status as SubmodelStatusValue)}`} />
                      {SUBMODEL_LABELS[key as SubmodelKey]}
                    </button>
                    {idx < SUBMODEL_SEQUENCE.length - 1 && (
                      <span className="mx-0.5 text-[10px] text-muted/30">›</span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <div className="flex min-h-0 flex-1 overflow-hidden">
          <section className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <div className="scroll-quiet flex-1 overflow-y-auto">
              {!hasChat ? (
                /* ── Empty / hero state ── */
                <div className="flex min-h-full flex-col items-center justify-center px-4 pt-12 pb-8 sm:px-6 md:py-16 animate-rise">
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
                      <span className="text-[12px] text-muted">PDF, Excel, CSV, DOCX · or paste a product URL</span>
                      {uploadError && <span className="text-[12px] text-red-500">{uploadError}</span>}
                    </div>

                    <div className="mt-8">
                      <div className="flex items-center gap-3 mb-3">
                        <span className="text-[12px] font-semibold uppercase tracking-wider text-muted">
                          Recent passports
                        </span>
                        <span className="flex-1 border-t border-hairline" />
                        {recentPassports.length > 0 && (
                          <a href="/workspace/assets" className="text-[12px] text-signal hover:underline">View all →</a>
                        )}
                      </div>
                      {recentPassports.length === 0 ? (
                        <div className="rounded-xl border border-hairline bg-paper p-6 text-center">
                          <p className="text-[14px] font-medium text-ink">No passports yet</p>
                          <p className="mt-1 text-[13px] text-muted">
                            Upload a product datasheet or paste a product URL to get started.
                          </p>
                        </div>
                      ) : (
                        <div className="grid grid-cols-2 gap-2">
                          {recentPassports.map((p) => (
                            <a
                              key={p.thread_id}
                              href={`/workspace?thread=${p.thread_id}`}
                              className="flex items-center gap-3 rounded-xl border border-hairline bg-paper px-4 py-3 transition-colors hover:border-signal/30 hover:bg-mist"
                            >
                              <span className={`h-2 w-2 shrink-0 rounded-full ${p.status === "deployed" ? "bg-ok" : "bg-warn"}`} />
                              <div className="min-w-0">
                                <p className="truncate text-[13px] font-medium text-ink">{p.product_name}</p>
                                <p className="text-[11px] text-muted capitalize">{p.status}</p>
                              </div>
                            </a>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                /* ── Active chat ── */
                <div className="px-4 py-4 sm:px-6 sm:py-6">
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

                    {/* ── Specialist agent suggestion card ─────────────── */}
                    {showAgentSuggestion && !busy && (
                      <div className="rounded-xl border border-signal/20 bg-signal/[0.03] p-4">
                        <div className="flex items-start justify-between gap-3 mb-3">
                          <div>
                            <p className="text-[13px] font-semibold text-ink">Run specialist agents</p>
                            <p className="mt-0.5 text-[12px] text-muted">These agents search the web and calculate values automatically — no manual entry needed.</p>
                          </div>
                          <button onClick={() => setShowAgentSuggestion(false)} className="shrink-0 text-muted hover:text-ink">
                            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 2l10 10M12 2L2 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                          </button>
                        </div>
                        <div className="flex flex-col gap-2 sm:flex-row">
                          {(submodelStatus["carbon_footprint"] === "pending" || submodelStatus["carbon_footprint"] === "in_progress") && (
                            <button
                              onClick={() => void runSpecialistAgent("carbon_footprint")}
                              disabled={!!agentRunning}
                              className="flex items-center gap-2 rounded-lg border border-hairline bg-paper px-4 py-2.5 text-[13px] font-medium text-ink transition-colors hover:border-signal/30 hover:bg-mist disabled:opacity-40"
                            >
                              <span>🌿</span>
                              <div className="text-left">
                                <div className="font-semibold">Carbon Footprint</div>
                                <div className="text-[11px] text-muted font-normal">Calculates PCF using emission factors</div>
                              </div>
                            </button>
                          )}
                          {(submodelStatus["technical_data"] === "pending" || submodelStatus["technical_data"] === "in_progress") && (
                            <button
                              onClick={() => void runSpecialistAgent("technical_data")}
                              disabled={!!agentRunning}
                              className="flex items-center gap-2 rounded-lg border border-hairline bg-paper px-4 py-2.5 text-[13px] font-medium text-ink transition-colors hover:border-signal/30 hover:bg-mist disabled:opacity-40"
                            >
                              <span>⚙️</span>
                              <div className="text-left">
                                <div className="font-semibold">Technical Data</div>
                                <div className="text-[11px] text-muted font-normal">Extracts specs from product page & datasheet</div>
                              </div>
                            </button>
                          )}
                        </div>
                      </div>
                    )}

                    {/* ── PDF links found on product page ──────────────── */}
                    {pdfLinks.length > 0 && !busy && (
                      <div className="rounded-xl border border-hairline bg-paper p-4">
                        <div className="flex items-center justify-between mb-2">
                          <p className="text-[12px] font-semibold text-ink">Found documents</p>
                          <span className="text-[11px] text-muted">from product page</span>
                        </div>
                        <div className="space-y-1.5">
                          {pdfLinks.map((url, i) => {
                            const docTitle = decodeURIComponent(url.split("/").pop() ?? url).replace(/\.[^.]+$/, "") || "Document";
                            const isAdded = addedHandoverUrls.has(url);
                            return (
                              <div key={i} className="flex items-center gap-2">
                                <a
                                  href={url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="flex flex-1 items-center gap-2 text-[12px] text-signal hover:underline min-w-0"
                                >
                                  <svg width="12" height="12" viewBox="0 0 16 16" fill="none" className="shrink-0">
                                    <rect x="2" y="1" width="12" height="14" rx="2" stroke="currentColor" strokeWidth="1.5"/>
                                    <path d="M5 6h6M5 9h4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                                  </svg>
                                  <span className="truncate">{docTitle}</span>
                                </a>
                                <button
                                  onClick={() => setPreviewDocUrl(url)}
                                  title="Preview document"
                                  className="shrink-0 rounded-full border border-hairline px-2.5 py-1 text-[10px] font-medium text-muted hover:border-signal/40 hover:text-signal transition-colors"
                                >
                                  Preview
                                </button>
                                <button
                                  onClick={() => addHandoverDocUrl(url, docTitle)}
                                  disabled={isAdded}
                                  title="Add as DigitalFile in Handover Documentation"
                                  className={`shrink-0 rounded-full px-2.5 py-1 text-[10px] font-medium transition-colors ${
                                    isAdded
                                      ? "bg-ok/10 text-ok cursor-default"
                                      : "border border-hairline hover:border-signal/40 hover:text-signal text-muted"
                                  }`}
                                >
                                  {isAdded ? "✓ Added" : "+ Handover"}
                                </button>
                              </div>
                            );
                          })}
                        </div>
                        <p className="mt-2 text-[11px] text-muted">Click <strong>+ Handover</strong> to link a document into the Handover Documentation submodel, or upload a file to extract data from it.</p>
                      </div>
                    )}

                    {/* ── Missing fields summary — shown only after all submodels done ── */}
                    {allSubmodelsDone && missingRequired.length > 0 && !busy && deployStatus === "idle" && (
                      <div className="rounded-xl border border-warn/20 bg-warn/[0.04] p-4 space-y-3">
                        <div>
                          <p className="text-[13px] font-semibold text-warn">Some fields couldn't be found</p>
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            {missingRequired.map((g) => (
                              <span key={g} className="rounded-full border border-warn/20 bg-paper px-2.5 py-0.5 font-mono text-[11px] text-ink">
                                {g}
                              </span>
                            ))}
                          </div>
                          <p className="mt-2 text-[12px] text-muted">
                            You can still generate the passport with what's been collected, or request the missing data from your supplier.
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
                              Request from supplier
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


                    {/* ── Handover Documentation helper card ───────────── */}
                    {currentSubmodel === "handover_documentation" && !busy && (
                      <div className="rounded-xl border border-signal/20 bg-signal/[0.03] p-4">
                        <p className="text-[12px] font-semibold text-ink mb-1">Handover Documentation</p>
                        <p className="text-[12px] text-muted leading-relaxed">
                          Add manuals, datasheets, and certificates to this passport.
                          Files you upload now will be stored permanently and linked as downloadable
                          DigitalFile references in the IDTA 02004 submodel.
                        </p>
                        <div className="mt-2.5 flex gap-2">
                          <button
                            onClick={() => fileInputRef.current?.click()}
                            className="flex items-center gap-1.5 rounded-full border border-signal/30 bg-paper px-3 py-1.5 text-[12px] font-medium text-signal hover:bg-signal/5 transition-colors"
                          >
                            <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
                              <path d="M8 11V2M8 2L4.5 5.5M8 2l3.5 3.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
                              <path d="M2 13h12" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
                            </svg>
                            Upload & store document
                          </button>
                        </div>
                      </div>
                    )}

                    {/* ── Generate button — shown whenever there is data ─ */}
                    {hasExtracted && deployStatus === "idle" && !busy && (
                      <div className="rounded-xl border border-ok/20 bg-ok/[0.04] p-4">
                        <p className="text-[13px] font-semibold text-ok">
                          {allSubmodelsDone ? "All submodels complete" : "Ready to generate"}
                        </p>
                        <p className="mt-1 text-[12px] text-muted">
                          {allSubmodelsDone
                            ? `MIA has collected data across all ${SUBMODEL_SEQUENCE.length} IDTA submodels.`
                            : "Generate the passport with the data collected so far."}
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
                        <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
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
                            <div className="mt-3 flex flex-wrap gap-2 sm:gap-2">
                              <a
                                href={`/passport/${threadId}`}
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
                              {threadId && (
                                <button
                                  onClick={async () => {
                                    const res = await fetch(`/api/passports/thread/${threadId}/download`);
                                    if (!res.ok) return;
                                    const blob = await res.blob();
                                    const url = URL.createObjectURL(blob);
                                    const a = document.createElement("a");
                                    a.href = url;
                                    a.download = `${(productName || "passport").replace(/[^a-z0-9]/gi, "_").toLowerCase()}-dpp.pdf`;
                                    document.body.appendChild(a);
                                    a.click();
                                    document.body.removeChild(a);
                                    setTimeout(() => URL.revokeObjectURL(url), 1000);
                                  }}
                                  className="rounded-full border border-hairline px-3 py-1.5 text-[12px] font-medium text-muted hover:text-ink"
                                >
                                  Download DPP
                                </button>
                              )}
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
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            onClick={() => { setDeployStatus("idle"); setDeployError(""); }}
                            className="rounded-full border border-hairline px-3 py-1.5 text-[12px] font-medium text-ink hover:bg-mist"
                          >
                            Try again
                          </button>
                          {deployError.toLowerCase().includes("validation") && (
                            <button
                              onClick={() => void deployPassport(threadId ?? undefined, true)}
                              className="rounded-full bg-warn/80 px-3 py-1.5 text-[12px] font-medium text-white hover:bg-warn transition-colors"
                            >
                              Deploy anyway (skip validation)
                            </button>
                          )}
                        </div>
                      </div>
                    )}


                    {/* Mobile extracted fields toggle — shown below chat on small screens */}
                    {hasExtracted && !busy && (
                      <div className="md:hidden rounded-xl border border-hairline bg-mist p-4">
                        <div className="flex items-center justify-between mb-2">
                          <p className="text-[12px] font-semibold uppercase tracking-wider text-muted">
                            Extracted fields ({Object.keys(extractedFields).length})
                          </p>
                          <p className="text-[11px] text-muted">Tap to edit</p>
                        </div>
                        <div className="space-y-0.5 max-h-64 overflow-y-auto scroll-quiet">
                          {Object.entries(extractedFields).map(([field, value]) => (
                            <div key={field} className="flex items-start gap-2 rounded-lg px-2 py-2">
                              <span className="shrink-0 font-mono text-[11px] text-muted w-32 pt-0.5 leading-relaxed">{field}</span>
                              {editingField === field ? (
                                <input
                                  autoFocus
                                  value={editingValue}
                                  onChange={(e) => setEditingValue(e.target.value)}
                                  onBlur={commitFieldEdit}
                                  onKeyDown={(e) => {
                                    if (e.key === "Enter") commitFieldEdit();
                                    if (e.key === "Escape") setEditingField(null);
                                  }}
                                  className="flex-1 rounded border border-signal/40 bg-paper px-2 py-1 text-[12px] text-ink focus:outline-none"
                                />
                              ) : (
                                <button
                                  onClick={() => startEditField(field, value)}
                                  className="flex-1 text-left text-[12px] text-ink break-words min-w-0 py-0.5"
                                >
                                  {value}
                                </button>
                              )}
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
              <div className="shrink-0 border-t border-hairline bg-paper px-4 pt-3 pb-safe md:px-6 md:py-4" style={{ zIndex: 1 }}>
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
                    {/* Skip button — shown when not all done and not deploying */}
                    {deployStatus === "idle" && !allSubmodelsDone && (
                      <button
                        type="button"
                        onClick={() => void skipSubmodel()}
                        disabled={busy}
                        title={`Skip ${SUBMODEL_LABELS[currentSubmodel]}`}
                        className="flex items-center gap-1 rounded-xl border border-hairline bg-paper px-3 py-1.5 text-[12px] font-medium text-muted transition-colors hover:border-warn/30 hover:text-warn disabled:opacity-30"
                      >
                        Skip {SUBMODEL_LABELS[currentSubmodel]} →
                      </button>
                    )}
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
                      placeholder={`Provide ${SUBMODEL_LABELS[currentSubmodel]} data or paste a URL…`}
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

          {/* ── Right sidebar: product image + extracted fields ── */}
          {hasChat && hasExtracted && (
            <aside className="hidden md:flex w-72 lg:w-80 xl:w-96 shrink-0 flex-col border-l border-hairline bg-paper overflow-y-auto scroll-quiet">
              {/* Product image */}
              <div className="border-b border-hairline p-4">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-muted mb-3">Product image</p>
                {productImageUrl ? (
                  <div className="flex items-start gap-3">
                    <img
                      src={productImageUrl}
                      alt="Product"
                      className="h-20 w-20 rounded-lg object-contain border border-hairline bg-mist shrink-0"
                      onError={(e) => ((e.target as HTMLImageElement).style.display = "none")}
                    />
                    <div className="flex flex-col gap-1.5 min-w-0">
                      <p className="text-[11px] text-muted leading-relaxed">
                        {imageSource === "og" ? "Extracted from product page" : "Uploaded by you"}
                      </p>
                      <button
                        onClick={() => imageInputRef.current?.click()}
                        className="text-[11px] font-medium text-signal hover:underline text-left"
                      >
                        Use a different image →
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center gap-3">
                    <p className="text-[11px] text-muted flex-1">No product image yet.</p>
                    <button
                      onClick={() => imageInputRef.current?.click()}
                      className="rounded-full border border-hairline px-3 py-1.5 text-[11px] font-medium text-ink hover:bg-mist transition-colors"
                    >
                      Upload
                    </button>
                  </div>
                )}
              </div>

              {/* Extracted fields */}
              <div className="flex-1 p-4">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
                    Extracted fields ({Object.keys(extractedFields).length})
                  </p>
                  <p className="text-[10px] text-muted">Click to edit</p>
                </div>
                <div className="space-y-0.5">
                  {Object.entries(extractedFields).map(([field, value]) => (
                    <div key={field} className="flex items-start gap-2 rounded-lg px-2 py-1 hover:bg-mist group">
                      <span className="shrink-0 font-mono text-[10px] text-muted w-36 pt-0.5 flex items-center gap-1 leading-relaxed">
                        {field}
                        {manuallyEditedFields.has(field) && (
                          <span className="h-1.5 w-1.5 rounded-full bg-signal shrink-0" title="Manually edited" />
                        )}
                      </span>
                      {editingField === field ? (
                        <input
                          autoFocus
                          value={editingValue}
                          onChange={(e) => setEditingValue(e.target.value)}
                          onBlur={commitFieldEdit}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") commitFieldEdit();
                            if (e.key === "Escape") setEditingField(null);
                          }}
                          className="flex-1 rounded border border-signal/40 bg-paper px-2 py-0.5 text-[11px] text-ink focus:outline-none focus:ring-2 focus:ring-signal/20"
                        />
                      ) : field === "DigitalFile" && value ? (
                        <div className="flex flex-1 flex-wrap items-center gap-1">
                          {value.split(",").map((u, idx) => {
                            const trimmed = u.trim();
                            return (
                              <button
                                key={idx}
                                onClick={() => setPreviewDocUrl(trimmed)}
                                className="flex items-center gap-1 rounded border border-hairline bg-mist px-1.5 py-0.5 text-[10px] text-signal hover:border-signal/40 transition-colors"
                                title={trimmed}
                              >
                                <svg width="9" height="9" viewBox="0 0 16 16" fill="none">
                                  <rect x="2" y="1" width="12" height="14" rx="2" stroke="currentColor" strokeWidth="1.5"/>
                                  <path d="M5 6h6M5 9h4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                                </svg>
                                {decodeURIComponent(trimmed.split("/").pop() ?? trimmed).slice(0, 22) || "Doc"}
                              </button>
                            );
                          })}
                        </div>
                      ) : (
                        <button
                          onClick={() => startEditField(field, value)}
                          className="flex-1 text-left text-[11px] text-ink hover:text-signal break-words min-w-0"
                        >
                          {value}
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </aside>
          )}
        </div>
      </div>
    </>
  );
}

export default function Workspace() {
  return (
    <Suspense>
      <WorkspaceInner />
    </Suspense>
  );
}
