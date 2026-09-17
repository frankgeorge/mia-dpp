"use client";

import { useState } from "react";

interface DataSource {
  id: string;
  name: string;
  description: string;
  connected: boolean;
  icon: React.ReactNode;
  fields?: { label: string; type: string; placeholder: string }[];
}

function DbIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="12" cy="5" rx="9" ry="3" />
      <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
    </svg>
  );
}

function FileIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

function GlobeIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="2" y1="12" x2="22" y2="12" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}

function MailIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
      <polyline points="22,6 12,13 2,6" />
    </svg>
  );
}

function CadIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="12 2 2 7 12 12 22 7 12 2" />
      <polyline points="2 17 12 22 22 17" />
      <polyline points="2 12 12 17 22 12" />
    </svg>
  );
}

const SECTIONS: { label: string; sources: DataSource[] }[] = [
  {
    label: "ERP & Manufacturing",
    sources: [
      {
        id: "sap",
        name: "SAP S/4HANA",
        description: "Pull material master and product data via OData",
        connected: false,
        icon: <DbIcon />,
        fields: [
          { label: "Hostname", type: "text", placeholder: "my-sap.example.com" },
          { label: "Client", type: "text", placeholder: "100" },
          { label: "Username", type: "text", placeholder: "SAPUSER" },
          { label: "Password", type: "password", placeholder: "Password" },
        ],
      },
      {
        id: "dynamics",
        name: "Microsoft Dynamics",
        description: "Connect to Dynamics 365 Business Central or F&O",
        connected: false,
        icon: <DbIcon />,
        fields: [
          { label: "Tenant ID", type: "text", placeholder: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" },
          { label: "Client ID", type: "text", placeholder: "App (client) ID" },
          { label: "Client Secret", type: "password", placeholder: "Client secret" },
        ],
      },
      {
        id: "odoo",
        name: "Odoo",
        description: "Import product records from Odoo via XML-RPC",
        connected: false,
        icon: <DbIcon />,
        fields: [
          { label: "URL", type: "url", placeholder: "https://mycompany.odoo.com" },
          { label: "Database", type: "text", placeholder: "mycompany" },
          { label: "API Key", type: "password", placeholder: "API key from user settings" },
        ],
      },
    ],
  },
  {
    label: "CAD & PDM",
    sources: [
      {
        id: "solidworks",
        name: "SolidWorks PDM",
        description: "Sync product metadata from SolidWorks PDM vault",
        connected: false,
        icon: <CadIcon />,
        fields: [
          { label: "Vault server", type: "text", placeholder: "pdm-server.local" },
          { label: "Vault name", type: "text", placeholder: "ProductVault" },
          { label: "Username", type: "text", placeholder: "pdm_user" },
          { label: "Password", type: "password", placeholder: "Password" },
        ],
      },
      {
        id: "teamcenter",
        name: "Teamcenter",
        description: "Connect to Siemens Teamcenter PLM REST API",
        connected: false,
        icon: <CadIcon />,
        fields: [
          { label: "Base URL", type: "url", placeholder: "https://tc.example.com" },
          { label: "Username", type: "text", placeholder: "tc_user" },
          { label: "Password", type: "password", placeholder: "Password" },
        ],
      },
    ],
  },
  {
    label: "Files & Documents",
    sources: [
      {
        id: "excel",
        name: "Excel / CSV",
        description: "Upload product data spreadsheets for extraction",
        connected: true,
        icon: <FileIcon />,
      },
      {
        id: "pdf",
        name: "PDF Datasheets",
        description: "Parse product specifications from PDF files",
        connected: true,
        icon: <FileIcon />,
      },
      {
        id: "sharepoint",
        name: "SharePoint",
        description: "Connect to Microsoft SharePoint document library",
        connected: false,
        icon: <FileIcon />,
        fields: [
          { label: "Tenant ID", type: "text", placeholder: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" },
          { label: "Site URL", type: "url", placeholder: "https://mycompany.sharepoint.com/sites/Products" },
          { label: "Client ID", type: "text", placeholder: "App registration client ID" },
          { label: "Client Secret", type: "password", placeholder: "Client secret" },
        ],
      },
    ],
  },
  {
    label: "Web",
    sources: [
      {
        id: "url",
        name: "Product URL",
        description: "Scrape product data from any public product page",
        connected: true,
        icon: <GlobeIcon />,
      },
    ],
  },
  {
    label: "Supplier",
    sources: [
      {
        id: "email",
        name: "Email Portal",
        description: "Send data-request emails and auto-receive supplier responses",
        connected: true,
        icon: <MailIcon />,
      },
    ],
  },
];

function ConnectModal({
  source,
  onClose,
}: {
  source: DataSource;
  onClose: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>({});

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 backdrop-blur-sm">
      <div className="w-full max-w-md animate-rise rounded-2xl bg-paper p-7 shadow-2xl">
        <div className="mb-5 flex items-center justify-between">
          <h3 className="text-[18px] font-semibold text-ink">Connect {source.name}</h3>
          <button
            onClick={onClose}
            className="grid h-8 w-8 place-items-center rounded-full text-muted hover:bg-mist hover:text-ink"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M1 1l12 12M13 1L1 13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <div className="space-y-4">
          {(source.fields ?? []).map((field) => (
            <div key={field.label}>
              <label className="mb-1.5 block text-[12px] font-medium text-muted">
                {field.label}
              </label>
              <input
                type={field.type}
                placeholder={field.placeholder}
                value={values[field.label] ?? ""}
                onChange={(e) => setValues((prev) => ({ ...prev, [field.label]: e.target.value }))}
                className="w-full rounded-xl border border-hairline bg-mist px-3 py-2.5 text-[13px] text-ink placeholder:text-muted focus:border-signal/50 focus:outline-none focus:ring-4 focus:ring-signal/10"
              />
            </div>
          ))}
        </div>

        <div className="mt-6 flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 rounded-full border border-hairline py-2.5 text-[13px] font-medium text-muted hover:text-ink"
          >
            Cancel
          </button>
          <button
            onClick={onClose}
            className="flex-1 rounded-full bg-ink py-2.5 text-[13px] font-medium text-white hover:opacity-90"
          >
            Save & connect
          </button>
        </div>
      </div>
    </div>
  );
}

function SourceCard({
  source,
  onConnect,
}: {
  source: DataSource;
  onConnect: (source: DataSource) => void;
}) {
  return (
    <div
      className={`flex flex-col rounded-xl border p-5 ${
        source.connected
          ? "border-ok/20 bg-ok/[0.03]"
          : "border-hairline bg-paper"
      }`}
    >
      <div
        className={`mb-3 grid h-10 w-10 place-items-center rounded-xl ${
          source.connected ? "bg-ok/10 text-ok" : "bg-mist text-muted"
        }`}
      >
        {source.icon}
      </div>
      <p className="text-[14px] font-semibold text-ink">{source.name}</p>
      <p className="mt-1 flex-1 text-[12px] leading-relaxed text-muted">
        {source.description}
      </p>
      <div className="mt-4">
        {source.connected ? (
          <div className="flex items-center gap-2">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <circle cx="7" cy="7" r="7" fill="#1B8A5A" fillOpacity="0.15" />
              <path d="M4 7l2 2 4-4" stroke="#1B8A5A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span className="text-[12px] font-medium text-ok">Connected</span>
          </div>
        ) : (
          <button
            onClick={() => onConnect(source)}
            className="rounded-full border border-signal/20 bg-signalDim px-4 py-1.5 text-[12px] font-medium text-signal transition-all hover:bg-signal/15"
          >
            Connect
          </button>
        )}
      </div>
    </div>
  );
}

export default function DataSourcesPage() {
  const [modalSource, setModalSource] = useState<DataSource | null>(null);

  return (
    <>
      {modalSource && (
        <ConnectModal source={modalSource} onClose={() => setModalSource(null)} />
      )}

      <div className="px-8 py-8">
        <div className="mx-auto max-w-shell">
          {/* Page header */}
          <div className="mb-8 flex items-start justify-between">
            <div>
              <h1 className="text-[22px] font-semibold tracking-tight text-ink">
                Data Sources
              </h1>
              <p className="mt-1 text-[14px] text-muted">
                Manage which systems MIA can pull product data from.
              </p>
            </div>
            <button className="flex items-center gap-2 rounded-full bg-ink px-4 py-2 text-[13px] font-medium text-white transition-all hover:-translate-y-px hover:shadow-md">
              <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
                <path d="M6.5 1v11M1 6.5h11" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              </svg>
              Add data source
            </button>
          </div>

          {/* Sections */}
          <div className="space-y-10">
            {SECTIONS.map((section) => (
              <div key={section.label}>
                <h2 className="mb-4 text-[12px] font-semibold uppercase tracking-wider text-muted">
                  {section.label}
                </h2>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {section.sources.map((source) => (
                    <SourceCard
                      key={source.id}
                      source={source}
                      onConnect={setModalSource}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
