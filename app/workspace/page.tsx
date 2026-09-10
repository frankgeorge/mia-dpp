"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import type {
  ChatMessage,
  DppPackage,
  FieldMapping,
  GraphEntry,
  NameplateElement,
  ProposedFieldMapping,
} from "@/lib/types";
import { MappingRow } from "@/components/MappingRow";
import { DppView } from "@/components/DppView";

const GRAPH_KEY = "mia.graph.v1";
const API_URL =
  process.env.NEXT_PUBLIC_MIA_API_URL ?? "http://127.0.0.1:8000";

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

export default function Workspace() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [mappings, setMappings] = useState<FieldMapping[]>([]);
  const [productName, setProductName] = useState("");
  const [dpp, setDpp] = useState<DppPackage | null>(null);
  const [graph, setGraph] = useState<GraphEntry[]>([]);
  const [nameplateElements, setNameplateElements] = useState<
    NameplateElement[]
  >([]);
  const [mode, setMode] = useState<string>("");
  const [tab, setTab] = useState<"mappings" | "graph">("mappings");
  const endRef = useRef<HTMLDivElement>(null);

  /* Integration Graph persists across sessions in the browser. */
  useEffect(() => {
    try {
      const raw = localStorage.getItem(GRAPH_KEY);
      if (raw) setGraph(JSON.parse(raw));
    } catch {
      /* ignore unreadable storage */
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(GRAPH_KEY, JSON.stringify(graph));
    } catch {
      /* ignore full or blocked storage */
    }
  }, [graph]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function send(text: string) {
    const t = text.trim();
    if (!t || busy) return;

    const next: ChatMessage[] = [...messages, { role: "user", content: t }];
    setMessages(next);
    setInput("");
    setBusy(true);

    try {
      const res = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: next, graph }),
      });
      if (!res.ok) throw new Error(`Python backend returned ${res.status}`);
      const data = await res.json();
      setMode(data.mode ?? "");
      setNameplateElements(data.nameplateElements ?? []);

      if (data.proposal) {
        setProductName(data.proposal.productName || "Product");
        setMappings(
          (data.proposal.mappings ?? []).map(
            (m: ProposedFieldMapping, i: number) => ({
              ...m,
              id: `${Date.now()}-${i}`,
            })
          )
        );
        setDpp(null);
        setTab("mappings");
      }

      if (data.generate) await generate();

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
                nameplateElements.find((e) => e.name === targetElement)
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

  /* Every human decision is written back — this is the compounding memory. */
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

  async function generate() {
    try {
      const response = await fetch(`${API_URL}/api/dpp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          productName: productName || "Product",
          mappings,
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

  const pending = mappings.filter((m) => m.status === "review").length;
  const ready = mappings.filter(
    (m) => m.status === "approved" || m.status === "auto"
  ).length;
  const present = new Set(
    mappings
      .filter(
        (mapping) =>
          mapping.status === "approved" || mapping.status === "auto"
      )
      .map((mapping) => mapping.targetElement)
  );
  const gaps = nameplateElements
    .filter((element) => element.required && !present.has(element.name))
    .map((element) => element.name);

  return (
    <div className="flex h-screen flex-col bg-mist">
      {/* Top bar */}
      <header className="relative z-10 flex h-14 shrink-0 items-center justify-between border-b border-hairline bg-paper px-5 shadow-sm">
        <div className="flex items-center gap-3">
          <Link href="/" className="flex items-center gap-2">
            <span className="grid h-6 w-6 place-items-center rounded-md bg-ink shadow-sm">
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
          <button
            onClick={generate}
            disabled={ready === 0}
            className="rounded-full bg-ink px-4 py-1.5 text-[13px] font-medium text-white transition-all hover:shadow-md hover:-translate-y-px disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:translate-y-0 disabled:hover:shadow-none"
          >
            Generate passport
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* Chat */}
        <section className="flex min-h-0 flex-1 flex-col border-hairline bg-[#F9FAFB] lg:max-w-[46%] lg:border-r">
          <div className="scroll-quiet flex-1 overflow-y-auto px-5 py-6">
            {messages.length === 0 && (
              <div className="mx-auto max-w-md pt-6">
                <h1 className="text-[26px] font-semibold leading-tight tracking-tight text-ink">
                  Describe a product.
                </h1>
                <p className="mt-2 text-[15px] leading-relaxed text-muted">
                  Manufacturer, model, serial number, year, plant, and any
                  technical values you have. MIA maps it to the IDTA Digital
                  Nameplate and stops wherever it needs your decision.
                </p>
                <div className="mt-8 space-y-3">
                  {SAMPLES.map((s) => (
                    <button
                      key={s.label}
                      onClick={() => send(s.text)}
                      className="w-full rounded-xl border border-hairline bg-white p-4 text-left transition-all hover:-translate-y-0.5 hover:border-signal/40 hover:bg-signal/5 hover:shadow-sm"
                    >
                      <p className="text-[14px] font-semibold text-ink">{s.label}</p>
                      <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-muted">
                        {s.text}
                      </p>
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="mx-auto max-w-md space-y-5">
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={m.role === "user" ? "flex justify-end" : "flex justify-start"}
                >
                  <div
                    className={
                      m.role === "user"
                        ? "max-w-[85%] rounded-2xl rounded-br-sm bg-gradient-to-tr from-signal to-blue-500 px-4 py-3 text-[14px] leading-relaxed text-white shadow-sm"
                        : "max-w-[92%] rounded-2xl rounded-bl-sm border border-hairline bg-white px-4 py-3 text-[14px] leading-relaxed text-ink shadow-sm"
                    }
                  >
                    {m.content}
                  </div>
                </div>
              ))}
              {busy && (
                <div className="flex gap-1.5 py-2 pl-2">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="h-1.5 w-1.5 animate-pulse rounded-full bg-signal/60"
                      style={{ animationDelay: `${i * 140}ms` }}
                    />
                  ))}
                </div>
              )}
              <div ref={endRef} />
            </div>
          </div>

          <div className="shrink-0 p-4 pb-6">
            <div className="mx-auto flex max-w-md items-end gap-2 rounded-[24px] border border-hairline bg-white p-1.5 shadow-sm transition-all focus-within:border-signal/50 focus-within:ring-4 focus-within:ring-signal/10">
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
                placeholder="Describe the product..."
                className="max-h-32 flex-1 resize-none bg-transparent px-4 py-2.5 text-[14px] leading-relaxed text-ink placeholder:text-muted focus:outline-none"
              />
              <button
                onClick={() => send(input)}
                disabled={busy || !input.trim()}
                className="mb-0.5 mr-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-full bg-ink text-white transition-transform hover:scale-105 disabled:scale-100 disabled:opacity-25"
                aria-label="Send message"
              >
                <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
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
        </section>

        {/* Right panel */}
        <section className="flex min-h-0 flex-1 flex-col bg-mist">
          <div className="flex shrink-0 items-center justify-between border-b border-hairline bg-paper px-5">
            <div className="flex">
              {(["mappings", "graph"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`relative px-4 py-4 text-[13px] font-medium capitalize transition-colors ${
                    tab === t ? "text-signal" : "text-muted hover:text-ink"
                  }`}
                >
                  {t === "graph" ? "Integration Graph" : "Mappings"}
                  {t === "graph" && graph.length > 0 && (
                    <span className="ml-1.5 rounded-full bg-mist px-1.5 py-0.5 font-mono text-[10px] text-ink">
                      {graph.length}
                    </span>
                  )}
                  {tab === t && (
                    <span className="absolute inset-x-3 -bottom-px h-[3px] rounded-t-full bg-signal" />
                  )}
                </button>
              ))}
            </div>
            {tab === "mappings" && pending > 0 && (
              <button
                onClick={approveAll}
                className="rounded-full border border-hairline px-4 py-1.5 text-[12px] font-medium transition-all hover:bg-mist hover:shadow-sm"
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
                  body="Send a product description and the proposed mappings will appear here for your approval."
                />
              ) : (
                <div className="space-y-5">
                  <div className="flex flex-wrap gap-3">
                    <Stat label="Ready" value={ready} tone="ok" />
                    <Stat label="Needs you" value={pending} tone="warn" />
                    <Stat label="Gaps" value={gaps.length} tone="plain" />
                  </div>

                  {gaps.length > 0 && (
                    <div className="rounded-xl border border-warn/20 bg-warn/[0.04] p-4 shadow-sm">
                      <p className="text-[13px] font-semibold text-warn">
                        Required elements still missing
                      </p>
                      <p className="mt-1.5 font-mono text-[12px] leading-relaxed text-ink/80">
                        {gaps.join(" · ")}
                      </p>
                      <p className="mt-2 text-[12px] text-muted">
                        Add these values in the chat. MIA will not invent them.
                      </p>
                    </div>
                  )}

                  <div className="space-y-3">
                    {mappings.map((m) => (
                      <MappingRow
                        key={m.id}
                        mapping={m}
                        elements={nameplateElements}
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
              <div className="space-y-3">
                <p className="pb-2 text-[13px] leading-relaxed text-muted">
                  Verified mappings reused across products. These raise MIA&rsquo;s
                  confidence on the next passport.
                </p>
                {graph.map((g) => (
                  <div
                    key={g.sourceField}
                    className="rounded-xl border border-hairline bg-paper p-4 shadow-sm transition-all hover:shadow-md"
                  >
                    <p className="font-mono text-[13px]">
                      {g.sourceField}{" "}
                      <span className="text-muted">&rarr;</span>{" "}
                      <span className="text-signal">{g.targetElement}</span>
                    </p>
                    <p className="mt-1.5 font-mono text-[11px] text-muted">
                      {g.semanticId} · verified {g.corrections}&times;
                    </p>
                  </div>
                ))}
                <div className="pt-2">
                  <button
                    onClick={() => setGraph([])}
                    className="text-[12px] text-muted underline underline-offset-2 hover:text-ink"
                  >
                    Clear graph
                  </button>
                </div>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
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
    <div className="flex flex-col rounded-xl border border-hairline bg-paper px-4 py-2.5 shadow-sm">
      <span className={`font-mono text-[18px] font-semibold tabular-nums ${cls}`}>
        {value}
      </span>
      <span className="mt-0.5 text-[12px] text-muted">{label}</span>
    </div>
  );
}

function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="mx-auto max-w-xs pt-20 text-center">
      <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-full bg-white shadow-sm border border-hairline text-muted">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
          <line x1="16" y1="13" x2="8" y2="13"></line>
          <line x1="16" y1="17" x2="8" y2="17"></line>
          <polyline points="10 9 9 9 8 9"></polyline>
        </svg>
      </div>
      <p className="text-[15px] font-semibold text-ink">{title}</p>
      <p className="mt-2 text-[13px] leading-relaxed text-muted">{body}</p>
    </div>
  );
}