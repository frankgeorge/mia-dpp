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
  const graphReadyRef = useRef(false);
  const endRef = useRef<HTMLDivElement>(null);

  /* Integration Graph persists across sessions in the browser. */
  useEffect(() => {
    const restore = setTimeout(() => {
      try {
        const saved = localStorage.getItem(GRAPH_KEY);
        if (saved) setGraph(JSON.parse(saved));
      } catch {
        /* ignore unreadable storage */
      } finally {
        graphReadyRef.current = true;
      }
    }, 0);
    return () => clearTimeout(restore);
  }, []);

  useEffect(() => {
    if (!graphReadyRef.current) return;
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

      let generationProduct = productName;
      let generationMappings = mappings;
      if (data.proposal) {
        generationProduct = data.proposal.productName || "Product";
        generationMappings = (data.proposal.mappings ?? []).map(
          (m: ProposedFieldMapping, i: number) => ({
            ...m,
            id: `${Date.now()}-${i}`,
          })
        );
        setProductName(generationProduct);
        setMappings(generationMappings);
        setDpp(null);
        setTab("mappings");
      }

      if (data.generate) {
        await generate(generationProduct, generationMappings);
      }

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

  function correct(id: string, selected: NameplateElement) {
    const mapping = mappings.find((item) => item.id === id);
    if (!mapping) return;
    const corrected: FieldMapping = {
      ...mapping,
      targetElement: selected.name,
      semanticId: selected.semanticId,
      target: selected.target,
      status: "approved",
      reasoning: "Corrected by you, and saved to the Integration Graph.",
    };
    setMappings((previous) =>
      previous.map((item) => (item.id === id ? corrected : item))
    );
    writeToGraph(corrected);
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

  async function generate(
    selectedProduct = productName,
    selectedMappings = mappings
  ) {
    try {
      const response = await fetch(`${API_URL}/api/dpp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          productName: selectedProduct || "Product",
          mappings: selectedMappings,
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
      .map((mapping) => mapping.target.instancePath.join("/"))
  );
  const gaps = nameplateElements
    .filter(
      (element) =>
        element.required && !present.has(element.target.instancePath.join("/"))
    )
    .map((element) => element.name);

  return (
    <div className="flex h-screen flex-col bg-mist">
      {/* Top bar */}
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
          <button
            onClick={() => void generate()}
            disabled={ready === 0}
            className="rounded-full bg-ink px-4 py-1.5 text-[13px] font-medium text-white transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-30"
          >
            Generate passport
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* Chat */}
        <section className="flex min-h-0 flex-1 flex-col border-hairline bg-paper lg:max-w-[46%] lg:border-r">
          <div className="scroll-quiet flex-1 overflow-y-auto px-5 py-6">
            {messages.length === 0 && (
              <div className="mx-auto max-w-md pt-6">
                <h1 className="text-[26px] font-semibold leading-tight tracking-tight">
                  Describe a product.
                </h1>
                <p className="mt-2 text-[15px] leading-relaxed text-muted">
                  Manufacturer, model, serial number, year, plant, and any
                  technical values you have. MIA maps it to the IDTA Digital
                  Nameplate and stops wherever it needs your decision.
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
              {busy && (
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

          <div className="shrink-0 border-t border-hairline p-4">
            <div className="mx-auto flex max-w-md items-end gap-2">
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
                placeholder="Describe the product, or ask to generate the passport"
                className="max-h-32 flex-1 resize-none rounded-2xl border border-hairline bg-paper px-4 py-3 text-[14px] leading-relaxed placeholder:text-muted focus:border-signal focus:outline-none"
              />
              <button
                onClick={() => send(input)}
                disabled={busy || !input.trim()}
                className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-ink text-white transition-opacity hover:opacity-85 disabled:opacity-25"
                aria-label="Send message"
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path
                    d="M8 13V3M8 3L3.5 7.5M8 3l4.5 4.5"
                    stroke="currentColor"
                    strokeWidth="1.6"
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
                  body="Send a product description and the proposed mappings will appear here for your approval."
                />
              ) : (
                <div className="space-y-4">
                  <div className="flex flex-wrap gap-2">
                    <Stat label="Ready" value={ready} tone="ok" />
                    <Stat label="Needs you" value={pending} tone="warn" />
                    <Stat label="Gaps" value={gaps.length} tone="plain" />
                  </div>

                  {gaps.length > 0 && (
                    <div className="rounded-xl border border-warn/25 bg-warn/[0.06] p-3.5">
                      <p className="text-[13px] font-medium text-warn">
                        Required elements still missing
                      </p>
                      <p className="mt-1 font-mono text-[12px] leading-relaxed text-ink/70">
                        {gaps.join(" · ")}
                      </p>
                      <p className="mt-1.5 text-[12px] text-muted">
                        Add these values in the chat. MIA will not invent them.
                      </p>
                    </div>
                  )}

                  <div className="space-y-2">
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
                      {g.semanticId} · verified {g.corrections}&times;
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
    <div className="rounded-lg border border-hairline bg-paper px-3 py-2">
      <span className={`font-mono text-[15px] tabular-nums ${cls}`}>
        {value}
      </span>
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
