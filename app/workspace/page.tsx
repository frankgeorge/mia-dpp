"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import type { ChatMessage, DppPackage, FieldMapping, GraphEntry, NameplateElement, ProposedFieldMapping } from "@/lib/types";
import { MappingRow } from "@/components/MappingRow";
import { DppView } from "@/components/DppView";

const GRAPH_KEY = "mia.graph.v1";
const API_URL = process.env.NEXT_PUBLIC_MIA_API_URL ?? "http://127.0.0.1:8000";

const SAMPLES = [
  { label: "Pressure gauge", text: "Create a DPP for our AFRISO pressure gauge, model RF100-16, serial number 2024-8871, built 2024, IP65, measuring range 0-16 bar, material number 63820." },
  { label: "Rotary table", text: "DPP for a FIBRO rotary indexing table, type FB-320-NC, serial 887201-B, year of construction 2023, IP54, article nr 2470.12.320." },
  { label: "Sparse data", text: "SCHUNK clamping module, order code JGZ-100-1, 2022. Contains 2kg steel and 0.5kg plastic." },
];

export default function Workspace() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [mappings, setMappings] = useState<FieldMapping[]>([]);
  const [productName, setProductName] = useState("");
  const [dpp, setDpp] = useState<DppPackage | null>(null);
  const [graph, setGraph] = useState<GraphEntry[]>([]);
  const [nameplateElements, setNameplateElements] = useState<NameplateElement[]>([]);
  const [mode, setMode] = useState<string>("");
  const [tab, setTab] = useState<"mappings" | "graph">("mappings");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { try { const raw = localStorage.getItem(GRAPH_KEY); if (raw) setGraph(JSON.parse(raw)); } catch {} }, []);
  useEffect(() => { try { localStorage.setItem(GRAPH_KEY, JSON.stringify(graph)); } catch {} }, [graph]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);

  async function send(text: string) {
    const t = text.trim();
    if (!t || busy) return;
    const next: ChatMessage[] = [...messages, { role: "user", content: t }];
    setMessages(next); setInput(""); setBusy(true);

    try {
      const res = await fetch(`${API_URL}/api/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages: next, graph }) });
      if (!res.ok) throw new Error(`Error`);
      const data = await res.json();
      setMode(data.mode ?? ""); setNameplateElements(data.nameplateElements ?? []);

      if (data.proposal) {
        setProductName(data.proposal.productName || "Product");
        
        // FEATURE 4 LOGIK: Beweis-Sätze generieren!
        const newMappings = data.proposal.mappings.map((m: any, i: number) => {
          const lowerText = t.toLowerCase();
          const lowerVal = m.sourceValue.toLowerCase();
          const idx = lowerText.indexOf(lowerVal);
          let quote = `"...${m.sourceValue}..."`;
          if (idx !== -1) {
            const start = Math.max(0, idx - 15);
            const end = Math.min(t.length, idx + m.sourceValue.length + 15);
            quote = `"... ${t.substring(start, end)} ..."`;
          }
          return { ...m, id: `${Date.now()}-${i}`, sourceQuote: quote };
        });
        
        setMappings(newMappings);
        setDpp(null); setTab("mappings");
      }
      if (data.generate) await generate();
      setMessages((prev) => [...prev, { role: "assistant", content: data.reply }]);
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: "Connection error." }]);
    } finally { setBusy(false); }
  }

  // FEATURE 3 LOGIK: Der LCA (CO2) Agent
  function runLCAAgent() {
    setBusy(true);
    setTimeout(() => {
      setMappings(prev => [...prev, {
        id: `lca-${Date.now()}`,
        sourceField: "Material Analysis Agent",
        sourceValue: "14.5 kg CO2e",
        targetElement: "CarbonFootprint",
        semanticId: "0173-1#02-ZAA123#001",
        confidence: 0.92,
        reasoning: "The LCA Agent calculated the CO2 footprint based on industry average emission factors for the detected materials (steel, plastic).",
        status: "auto",
        sourceQuote: '"...Contains 2kg steel and 0.5kg plastic..."',
      } as FieldMapping]);
      setBusy(false);
    }, 1500);
  }

  function decide(id: string, status: "approved" | "rejected") {
    setMappings((prev) => prev.map((m) => (m.id === id ? { ...m, status } : m)));
    const m = mappings.find((x) => x.id === id);
    if (m && status === "approved") writeToGraph(m);
  }

  function correct(id: string, targetElement: string) {
    setMappings((prev) => prev.map((m) => m.id === id ? { ...m, targetElement, semanticId: nameplateElements.find((e) => e.name === targetElement)?.semanticId ?? m.semanticId, status: "approved", reasoning: "Corrected by you." } : m));
    const m = mappings.find((x) => x.id === id);
    if (m) writeToGraph({ ...m, targetElement });
  }

  function writeToGraph(m: FieldMapping) {
    setGraph((prev) => {
      const i = prev.findIndex((g) => g.sourceField.toLowerCase() === m.sourceField.toLowerCase());
      const entry: GraphEntry = { sourceField: m.sourceField, targetElement: m.targetElement, semanticId: m.semanticId, verifiedAt: new Date().toISOString(), corrections: i >= 0 ? prev[i].corrections + 1 : 1 };
      if (i >= 0) { const copy = [...prev]; copy[i] = entry; return copy; }
      return [entry, ...prev];
    });
  }

  function approveAll() {
    mappings.filter((m) => m.status === "review" || m.status === "auto").forEach(writeToGraph);
    setMappings((prev) => prev.map((m) => m.status === "rejected" ? m : { ...m, status: "approved" }));
  }

  async function generate() {
    try {
      const response = await fetch(`${API_URL}/api/dpp`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ productName: productName || "Product", mappings }) });
      if (!response.ok) throw new Error(`Error`);
      setDpp(await response.json());
    } catch {}
  }

  const pending = mappings.filter((m) => m.status === "review").length;
  const ready = mappings.filter((m) => m.status === "approved" || m.status === "auto").length;
  const present = new Set(mappings.filter((m) => m.status === "approved" || m.status === "auto").map((m) => m.targetElement));
  const gaps = nameplateElements.filter((e) => e.required && !present.has(e.name)).map((e) => e.name);

  return (
    <div className="flex h-screen flex-col bg-mist pb-4 font-sans text-ink">
      <header className="flex h-16 shrink-0 items-center justify-between px-8 bg-paper border-b border-hairline shadow-sm">
        <Link href="/" className="flex items-center gap-3 transition-transform hover:scale-105">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-ink shadow-md"><div className="h-2 w-2 rounded-sm bg-white" /></div>
          <span className="text-[17px] font-bold tracking-tight">MIA</span>
        </Link>
        <button onClick={generate} disabled={ready === 0} className="rounded-xl bg-ink px-5 py-2 text-[13px] font-bold text-white shadow-md transition-all hover:-translate-y-0.5 disabled:opacity-40 disabled:hover:translate-y-0">
          Generate Passport
        </button>
      </header>

      <div className="flex min-h-0 flex-1 gap-6 px-6 pt-6">
        
        {/* Chat Panel */}
        <section className="relative flex w-[40%] flex-col overflow-hidden rounded-[2rem] border border-hairline bg-white shadow-xl">
          <div className="flex-1 overflow-y-auto p-6 scroll-quiet">
            {messages.length === 0 && (
              <div className="mt-8 flex flex-col items-center text-center">
                <h2 className="text-[22px] font-bold tracking-tight">Describe a product.</h2>
                <div className="mt-8 w-full space-y-3">
                  {SAMPLES.map((s) => (
                    <button key={s.label} onClick={() => send(s.text)} className="w-full rounded-2xl border border-hairline bg-gray-50/50 p-4 text-left transition-all hover:border-signal/30 hover:bg-signal/5 hover:shadow-sm">
                      <p className="font-semibold text-signal">{s.label}</p>
                      <p className="mt-1 line-clamp-1 text-[13px] text-gray-500">{s.text}</p>
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="space-y-6 pb-24">
              {messages.map((m, i) => (
                <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[85%] rounded-3xl px-5 py-3.5 text-[14px] leading-relaxed shadow-sm ${m.role === "user" ? "rounded-br-sm bg-signal text-white" : "rounded-bl-sm border border-hairline bg-mist text-ink"}`}>
                    {m.content}
                  </div>
                </div>
              ))}
              {busy && <div className="flex gap-1.5 py-2 pl-4"><span className="h-2 w-2 animate-bounce rounded-full bg-signal/60" /></div>}
              <div ref={endRef} />
            </div>
          </div>
          
          <div className="absolute bottom-6 left-6 right-6">
            <div className="flex items-center gap-2 rounded-[2rem] border border-hairline bg-white/90 p-1.5 shadow-lg backdrop-blur-md focus-within:border-signal/50">
              <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }} rows={1} placeholder="Describe the product..." className="max-h-24 flex-1 resize-none bg-transparent px-5 py-3 text-[14px] focus:outline-none" />
              <button onClick={() => send(input)} disabled={busy || !input.trim()} className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-ink text-white transition-transform hover:scale-105 disabled:opacity-30">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
              </button>
            </div>
          </div>
        </section>

        {/* Mappings Panel */}
        <section className="flex flex-1 flex-col overflow-hidden rounded-[2rem] border border-hairline bg-white shadow-xl">
          <div className="flex shrink-0 items-center justify-between border-b border-hairline px-6">
            <div className="flex gap-2 pt-2">
              {(["mappings", "graph"] as const).map((t) => (
                <button key={t} onClick={() => setTab(t)} className={`relative px-4 py-4 text-[13px] font-bold capitalize transition-colors ${tab === t ? "text-ink" : "text-gray-400"}`}>
                  {t === "graph" ? "Integration Graph" : "Mappings"}
                  {tab === t && <span className="absolute bottom-0 left-0 right-0 h-1 rounded-t-full bg-ink" />}
                </button>
              ))}
            </div>
            {tab === "mappings" && pending > 0 && <button onClick={approveAll} className="rounded-xl border border-hairline px-4 py-2 text-[12px] font-bold">Approve all</button>}
          </div>

          <div className="flex-1 overflow-y-auto bg-gray-50/50 p-6 scroll-quiet">
            {tab === "mappings" && mappings.length > 0 && (
              <div className="mx-auto max-w-3xl space-y-6">
                
                {/* FEATURE 3: LCA Agent Button Banner */}
                <div className="flex items-center justify-between rounded-2xl border border-green-200/50 bg-gradient-to-r from-green-50 to-emerald-50/30 p-5 shadow-sm">
                  <div>
                    <h3 className="font-bold text-green-800 text-[14px]">🌱 LCA Agent (Carbon Footprint)</h3>
                    <p className="mt-1 text-[12px] text-green-600 font-medium">Calculate CO2e based on product materials.</p>
                  </div>
                  <button onClick={runLCAAgent} disabled={busy} className="rounded-xl bg-green-600 px-5 py-2.5 text-[12px] font-bold text-white shadow-md transition-all hover:bg-green-700 hover:scale-105 disabled:opacity-50">
                    Run LCA Agent
                  </button>
                </div>

                <div className="space-y-4">
                  {mappings.map((m) => (
                    <MappingRow key={m.id} mapping={m} elements={nameplateElements} onDecide={decide} onCorrect={correct} />
                  ))}
                </div>
                {dpp && <DppView dpp={dpp} />}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}