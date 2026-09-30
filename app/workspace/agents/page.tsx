"use client";

export default function AgentsPage() {
  return (
    <div className="px-8 py-8">
      <div className="mx-auto max-w-shell">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-[22px] font-semibold tracking-tight text-ink">Agents</h1>
          <p className="mt-1 text-[14px] text-muted">
            Specialist AI agents that run automatically inside your passport chats.
          </p>
        </div>

        {/* How it works */}
        <div className="mb-8 rounded-2xl border border-hairline bg-paper p-6">
          <p className="text-[13px] font-semibold text-ink mb-1">How agents work in MIA</p>
          <p className="text-[13px] text-muted leading-relaxed">
            Agents are invoked inline in the chat — not on this page. After you paste a product URL or upload a document, MIA will offer to run the relevant agents automatically. Each agent searches the web, reads product pages and datasheets, reasons over the data, and fills in the corresponding passport submodel fields. You can also trigger them manually from the suggestion card in the chat.
          </p>
        </div>

        {/* Agent cards */}
        <div className="grid gap-4 sm:grid-cols-2">
          <AgentCard
            icon="🌿"
            name="Carbon Footprint Calculator"
            standard="IDTA 02023"
            status="active"
            description="Calculates a Product Carbon Footprint (PCF) for an industrial product using web search and emission factor databases."
            howItWorks={[
              "Fetches the product page to identify materials and weight",
              "Searches for manufacturer sustainability data and green energy use",
              "Looks up emission factors for each identified material",
              "Applies GHG Protocol formula: PCF = Σ(weight × emission factor)",
              "Adjusts manufacturing energy if 100% renewable energy is confirmed",
            ]}
            outputFields={[
              "PCFCO2eq — total CO₂ equivalent in kg",
              "PCFLiveCyclePhase — cradle-to-gate (A1–A3)",
              "PCFCalculationMethod — GHG Protocol or ISO 14067",
              "PublicationDate & ExpirationDate",
              "ExplanatoryStatement — methodology summary",
            ]}
            triggeredBy="Product URL ingested in chat"
          />

          <AgentCard
            icon="⚙️"
            name="Technical Data Expert"
            standard="IDTA 02003"
            status="active"
            description="Extracts complete technical specifications from product pages and datasheets — no manual entry needed."
            howItWorks={[
              "Fetches the product page for basic specs (voltage, IP class, temperature range)",
              "Searches for and fetches the manufacturer datasheet PDF",
              "Extracts all technical properties with units",
              "Identifies certifications, approvals, and compliance standards",
              "Structures data into IDTA 02003-compatible field names",
            ]}
            outputFields={[
              "GeneralInformation — full technical description",
              "ProtectionClass — IP rating with standard reference",
              "SupplyVoltage, PowerConsumption, AmbientTemperature",
              "Approvals — CE, VDE, UL, RoHS, ATEX, etc.",
              "Dimensions, Weight, CableLength with units",
            ]}
            triggeredBy="Product URL ingested in chat"
          />
        </div>

        {/* Coming soon */}
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <ComingSoonCard
            icon="📄"
            name="Document Summariser"
            description="Reads multi-page PDFs, extracts all relevant product data across every submodel in a single pass."
          />
          <ComingSoonCard
            icon="🔗"
            name="Supplier Data Connector"
            description="Contacts suppliers automatically via email and ingests their responses into the passport."
          />
        </div>
      </div>
    </div>
  );
}

function AgentCard({
  icon,
  name,
  standard,
  status,
  description,
  howItWorks,
  outputFields,
  triggeredBy,
}: {
  icon: string;
  name: string;
  standard: string;
  status: "active" | "beta";
  description: string;
  howItWorks: string[];
  outputFields: string[];
  triggeredBy: string;
}) {
  return (
    <div className="flex flex-col rounded-2xl border border-hairline bg-paper overflow-hidden">
      {/* Card header */}
      <div className="flex items-start gap-4 p-5 border-b border-hairline">
        <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-hairline bg-mist text-[22px]">
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-[14px] font-semibold text-ink">{name}</p>
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
              status === "active" ? "bg-ok/10 text-ok" : "bg-warn/10 text-warn"
            }`}>
              {status === "active" ? "Active" : "Beta"}
            </span>
          </div>
          <p className="mt-0.5 font-mono text-[11px] text-muted">{standard}</p>
        </div>
      </div>

      {/* Description */}
      <div className="px-5 pt-4 pb-2">
        <p className="text-[13px] text-muted leading-relaxed">{description}</p>
      </div>

      {/* How it works */}
      <div className="px-5 pt-3">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted mb-2">How it works</p>
        <ol className="space-y-1">
          {howItWorks.map((step, i) => (
            <li key={i} className="flex items-start gap-2 text-[12px] text-ink">
              <span className="shrink-0 mt-0.5 font-mono text-[10px] text-muted">{i + 1}.</span>
              {step}
            </li>
          ))}
        </ol>
      </div>

      {/* Output fields */}
      <div className="px-5 pt-4">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted mb-2">Output fields</p>
        <div className="space-y-1">
          {outputFields.map((f, i) => (
            <p key={i} className="text-[12px] text-ink">
              <span className="font-mono text-signal">{f.split(" — ")[0]}</span>
              {f.includes(" — ") && <span className="text-muted"> — {f.split(" — ")[1]}</span>}
            </p>
          ))}
        </div>
      </div>

      {/* Footer */}
      <div className="mt-4 px-5 py-3 border-t border-hairline bg-mist/50">
        <p className="text-[11px] text-muted">
          <span className="font-medium text-ink">Triggered by:</span> {triggeredBy}
        </p>
      </div>
    </div>
  );
}

function ComingSoonCard({
  icon,
  name,
  description,
}: {
  icon: string;
  name: string;
  description: string;
}) {
  return (
    <div className="flex items-start gap-4 rounded-2xl border border-dashed border-hairline p-5 opacity-60">
      <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-hairline bg-mist text-[22px]">
        {icon}
      </div>
      <div>
        <div className="flex items-center gap-2">
          <p className="text-[14px] font-semibold text-ink">{name}</p>
          <span className="rounded-full bg-muted/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted">
            Soon
          </span>
        </div>
        <p className="mt-1 text-[13px] text-muted leading-relaxed">{description}</p>
      </div>
    </div>
  );
}
