import Link from "next/link";
import { Nameplate } from "@/components/Nameplate";

export default function Home() {
  return (
    <main className="min-h-screen bg-[#FAFAFC] selection:bg-signal selection:text-white text-ink overflow-hidden">
      
      {/* GLOWING BACKGROUND ANIMATION */}
      <div className="absolute top-[-10%] left-[-10%] w-[120%] h-[500px] bg-[radial-gradient(ellipse_at_top_center,rgba(11,95,208,0.15),transparent_50%)] pointer-events-none" />

      {/* Nav */}
      <header className="sticky top-0 z-50 border-b border-gray-200/50 bg-white/70 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-shell items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-3 transition-transform hover:scale-105">
            <Mark />
            <span className="text-[17px] font-bold tracking-tight">MIA</span>
          </Link>
          <nav className="hidden items-center gap-8 text-[14px] font-medium text-gray-500 md:flex">
            <a href="#how" className="transition-colors hover:text-signal">How it works</a>
            <a href="#gates" className="transition-colors hover:text-signal">Approval gates</a>
            <a href="#graph" className="transition-colors hover:text-signal">Integration Graph</a>
          </nav>
          <Link
            href="/workspace"
            className="rounded-full bg-ink px-5 py-2 text-[14px] font-semibold text-white shadow-md transition-all hover:-translate-y-0.5 hover:shadow-lg"
          >
            Try for free
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section className="relative mx-auto max-w-shell px-6 pb-24 pt-20 md:pt-32">
        <div className="grid items-center gap-16 md:grid-cols-2">
          <div className="relative z-10">
            <div className="animate-rise inline-flex items-center gap-2 rounded-full border border-signal/20 bg-signal/5 px-3 py-1.5 shadow-sm">
              <span className="h-2 w-2 rounded-full bg-signal animate-pulse" />
              <p className="font-mono text-[11px] font-bold uppercase tracking-[0.15em] text-signal">
                IDTA Digital Nameplate · ESPR ready
              </p>
            </div>
            
            <h1 className="mt-6 animate-rise text-[46px] font-black leading-[1.05] tracking-tight md:text-[64px]" style={{ animationDelay: "60ms" }}>
              Your product data
              <br />
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-ink to-gray-400">already exists.</span>
              <br />
              <span className="text-gray-400 text-[40px] md:text-[50px]">It just isn&rsquo;t readable.</span>
            </h1>
            
            <p className="mt-6 max-w-md animate-rise text-[18px] leading-relaxed text-gray-500 font-medium" style={{ animationDelay: "120ms" }}>
              MIA reads the exports, spreadsheets and datasheets you already have
              and turns them into a compliant Digital Product Passport. Agents do
              the mapping. You approve every decision before anything ships.
            </p>
            
            <div className="mt-10 flex animate-rise flex-wrap items-center gap-4" style={{ animationDelay: "180ms" }}>
              <Link href="/workspace" className="rounded-full bg-gradient-to-r from-signal to-blue-500 px-8 py-4 text-[15px] font-bold text-white shadow-lg shadow-signal/30 transition-all hover:-translate-y-1 hover:shadow-signal/50">
                Try for free
              </Link>
              <a href="#how" className="rounded-full border border-gray-200 bg-white px-8 py-4 text-[15px] font-semibold shadow-sm transition-all hover:-translate-y-1 hover:shadow-md">
                See how it works
              </a>
            </div>
            <p className="mt-6 animate-rise text-[13px] font-medium text-gray-400 flex items-center gap-2" style={{ animationDelay: "220ms" }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
              No account. Runs in your browser.
            </p>
          </div>

          <div className="relative animate-rise" style={{ animationDelay: "240ms" }}>
            <div className="absolute -inset-4 rounded-[3rem] bg-gradient-to-tr from-signal/10 to-blue-400/10 shadow-2xl opacity-60 blur-2xl"></div>
            <Nameplate />
          </div>
        </div>
      </section>

      {/* Problem strip */}
      <section className="bg-white py-20 border-y border-gray-100 relative z-10 shadow-sm">
        <div className="mx-auto max-w-shell px-6">
          <div className="grid gap-8 md:grid-cols-3">
            {[
              { stat: "One or two", label: "people handle compliance at a typical Mittelstand manufacturer. Not a team. Not a department." },
              { stat: "Six figures", label: "is what a consultancy charges to connect one legacy system to one data standard." },
              { stat: "Already live", label: "Digital Product Passport rules are in force for some categories and expanding to more." },
            ].map((c, i) => (
              <div key={i} className="rounded-3xl border border-gray-100 bg-[#FAFAFC] p-8 shadow-sm transition-all duration-300 hover:-translate-y-2 hover:shadow-xl hover:border-signal/30">
                <p className="text-[32px] font-black tracking-tight text-signal">{c.stat}</p>
                <p className="mt-3 text-[15px] leading-relaxed text-gray-500 font-medium">{c.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works (Die 4 Agenten) */}
      <section id="how" className="mx-auto max-w-shell px-6 py-32">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <h2 className="text-[36px] font-black leading-tight tracking-tight md:text-[46px]">
            Four agents. One pass. <br/><span className="text-signal">Every step reversible.</span>
          </h2>
          <p className="mt-6 text-[18px] leading-relaxed text-gray-500 font-medium">
            Each agent does one job and hands off. The order matters, so it&rsquo;s numbered.
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-2">
          {[
            { n: "01", t: "Reading", d: "Pulls fields out of whatever you have — an SAP table export, an Excel parts list, a scanned datasheet — and normalises them into one consistent shape." },
            { n: "02", t: "Mapping", d: "Matches each field to its place in the IDTA Digital Nameplate submodel, and scores how sure it is. Confident matches move on. Anything doubtful stops for you." },
            { n: "03", t: "Checking", d: "Verifies the package against the standard's required elements before it can be exported. Gaps are reported, never quietly filled." },
            { n: "04", t: "Watching", d: "After go-live, notices when a source field is renamed or disappears. Applies the fix it already knows, escalates anything new." },
          ].map((s) => (
            <div key={s.n} className="group rounded-[2rem] border border-gray-200 bg-white p-10 shadow-md transition-all duration-300 hover:-translate-y-2 hover:shadow-2xl hover:border-signal/50 relative overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-signal/5 to-transparent rounded-bl-full pointer-events-none transition-all group-hover:from-signal/20"></div>
              <div className="mb-6 flex h-14 w-14 items-center justify-center rounded-2xl bg-signal/10 transition-colors group-hover:bg-signal">
                <p className="font-mono text-[18px] font-black text-signal group-hover:text-white">{s.n}</p>
              </div>
              <h3 className="text-[24px] font-bold tracking-tight">{s.t}</h3>
              <p className="mt-3 text-[16px] leading-relaxed text-gray-500 font-medium">{s.d}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Gates */}
      <section id="gates" className="border-y border-gray-100 bg-white py-32 relative overflow-hidden">
        <div className="absolute right-[-10%] top-1/2 -z-10 h-[500px] w-[500px] -translate-y-1/2 rounded-full bg-signal/5 blur-[100px]" />
        <div className="mx-auto max-w-shell px-6">
          <div className="grid gap-16 md:grid-cols-2 items-center">
            <div>
              <h2 className="text-[36px] font-black leading-tight tracking-tight md:text-[46px]">
                Agents execute.
                <br />
                You decide.
              </h2>
              <p className="mt-6 max-w-md text-[18px] leading-relaxed text-gray-500 font-medium">
                Nothing reaches a passport without a person approving it. Every
                mapping carries its confidence score, the field it came from, and
                the reason it was chosen — so an auditor can follow the trail back.
              </p>
            </div>
            <div className="rounded-[2rem] border border-gray-200/60 bg-gray-50/50 p-6 shadow-2xl backdrop-blur-sm">
              <div className="space-y-4">
                {[
                  { c: 0.97, s: "NAME1", t: "ManufacturerName" },
                  { c: 0.94, s: "SCHUTZART", t: "DegreeOfProtection" },
                  { c: 0.64, s: "BAUJAHR", t: "YearOfConstruction" },
                ].map((r) => (
                  <div key={r.s} className="flex items-center gap-4 rounded-2xl border border-gray-100 bg-white p-5 shadow-sm transition-transform hover:scale-[1.02]">
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-mono text-[14px] font-semibold">
                        {r.s} <span className="text-gray-300 mx-2">&rarr;</span> {r.t}
                      </p>
                      <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
                        <div className="h-full rounded-full transition-all duration-1000" style={{ width: `${r.c * 100}%`, background: r.c >= 0.85 ? "#10B981" : "#F97316" }} />
                      </div>
                    </div>
                    <span className={`shrink-0 rounded-xl px-3 py-1.5 text-[12px] font-bold uppercase tracking-wide border ${r.c >= 0.85 ? "bg-green-50 text-green-600 border-green-200" : "bg-orange-50 text-orange-600 border-orange-200"}`}>
                      {r.c >= 0.85 ? "Cleared" : "Needs you"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Graph */}
      <section id="graph" className="mx-auto max-w-shell px-6 py-32">
        <div className="grid gap-16 md:grid-cols-2 md:items-center">
          <div className="order-2 md:order-1 rounded-[2rem] border border-gray-200 bg-white p-10 shadow-xl">
            <div className="flex items-end gap-6">
              {[
                { l: "1st", h: 100, v: "12 checks" },
                { l: "2nd", h: 62, v: "7 checks" },
                { l: "3rd", h: 34, v: "4 checks" },
              ].map((b, i) => (
                <div key={b.l} className="group flex-1 text-center">
                  <div className="flex h-48 items-end rounded-xl bg-gray-50 border border-gray-100 p-2">
                    <div
                      className="w-full rounded-lg transition-all duration-500 group-hover:opacity-100"
                      style={{
                        height: `${b.h}%`,
                        background: i === 2 ? "linear-gradient(to top, #0B5FD0, #4A90E2)" : "#CBD5E1",
                        opacity: i === 2 ? 1 : 0.5,
                        boxShadow: i === 2 ? "0 10px 20px -5px rgba(11, 95, 208, 0.4)" : "none"
                      }}
                    />
                  </div>
                  <p className="mt-4 font-mono text-[14px] font-bold text-ink">{b.l}</p>
                  <p className="mt-1 text-[13px] font-medium text-gray-500">{b.v}</p>
                </div>
              ))}
            </div>
            <p className="mt-8 border-t border-gray-100 pt-6 text-[14px] font-medium text-gray-500 text-center">
              Manual checks needed per passport, same product family.
            </p>
          </div>
          <div className="order-1 md:order-2 pl-0 md:pl-8">
            <h2 className="text-[36px] font-black leading-tight tracking-tight md:text-[46px]">
              It gets faster
              <br />
              <span className="text-signal">with every product.</span>
            </h2>
            <p className="mt-6 max-w-md text-[18px] leading-relaxed text-gray-500 font-medium">
              Every correction you make is written back to the Integration Graph.
              The next product that uses the same field starts from your decision
              instead of from a guess. The second passport takes less of your
              time than the first.
            </p>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="relative overflow-hidden bg-ink py-32 text-white mt-10">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(11,95,208,0.3)_0%,transparent_70%)]"></div>
        <div className="relative z-10 mx-auto max-w-shell px-6 text-center">
          <h2 className="mx-auto max-w-2xl text-[40px] font-black leading-tight tracking-tight md:text-[56px]">
            Make a passport for one of your products right now.
          </h2>
          <p className="mx-auto mt-6 max-w-md text-[18px] leading-relaxed text-white/70 font-medium">
            Describe the product in your own words. MIA does the rest, and stops
            wherever it needs you.
          </p>
          <Link
            href="/workspace"
            className="mt-10 inline-flex items-center gap-2 rounded-full bg-white px-8 py-4 text-[16px] font-bold text-ink shadow-[0_0_40px_rgba(255,255,255,0.3)] transition-transform hover:scale-105"
          >
            Open Workspace
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
          </Link>
        </div>
      </section>

      <footer className="bg-ink border-t border-white/10">
        <div className="mx-auto max-w-shell px-6 py-8">
          <div className="flex flex-col justify-between gap-4 text-[13px] text-white/40 font-medium md:flex-row items-center">
            <p className="flex items-center gap-2">
              <span className="h-3 w-3 rounded-sm bg-white/40" />
              MIA - Mittelstand Integration Agent
            </p>
            <p className="font-mono text-[11px] tracking-widest uppercase">
              Built for the LEVEL3 AI Engineering track
            </p>
          </div>
        </div>
      </footer>
    </main>
  );
}

function Mark() {
  return (
    <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-ink to-gray-700 shadow-md">
      <div className="h-2 w-2 rounded-sm bg-white" />
    </div>
  );
}