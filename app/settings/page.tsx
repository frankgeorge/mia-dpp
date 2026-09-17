"use client";

import { useState } from "react";
import Link from "next/link";

const SETTINGS_KEY = "mia.settings.v1";

interface OrgSettings {
  orgName: string;
  logoUrl: string;
  brandColor: string;
  sapHost: string;
  sapClient: string;
  sapUsername: string;
  sapPassword: string;
}

const DEFAULTS: OrgSettings = {
  orgName: "",
  logoUrl: "",
  brandColor: "#0B5FD0",
  sapHost: "",
  sapClient: "100",
  sapUsername: "",
  sapPassword: "",
};

function load(): OrgSettings {
  if (typeof window === "undefined") return DEFAULTS;
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : DEFAULTS;
  } catch {
    return DEFAULTS;
  }
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<OrgSettings>(load);
  const [saved, setSaved] = useState(false);
  const [sapTesting, setSapTesting] = useState(false);
  const [sapStatus, setSapStatus] = useState<"idle" | "ok" | "error">("idle");
  const [sapError, setSapError] = useState("");
  const [testMaterial, setTestMaterial] = useState("");

  function set(key: keyof OrgSettings, value: string) {
    setSettings((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  }

  function save() {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
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

  return (
    <div className="min-h-screen bg-[#F5F5F7]" style={{ fontFamily: "Inter, system-ui, sans-serif" }}>
      {/* Header */}
      <header className="flex h-14 items-center justify-between border-b border-[#DCDCE0] bg-white px-6">
        <div className="flex items-center gap-3">
          <Link href="/workspace" className="flex items-center gap-2">
            <span className="grid h-6 w-6 place-items-center rounded-md bg-[#17181A]">
              <span className="h-1.5 w-1.5 rounded-[1px] bg-white" />
            </span>
            <span className="text-[15px] font-semibold tracking-tight text-[#17181A]">MIA</span>
          </Link>
          <span className="text-[13px] text-[#6E6E73]">/ Settings</span>
        </div>
        <Link
          href="/workspace"
          className="text-[13px] text-[#6E6E73] hover:text-[#17181A]"
        >
          Back to workspace
        </Link>
      </header>

      <div className="mx-auto max-w-2xl px-6 py-10 space-y-8">

        {/* ── Branding ──────────────────────────────────────────────────── */}
        <Section title="Supplier portal branding" description="Customise how your supplier portal looks when MIA requests missing product data.">
          <Field label="Organisation name" hint="Shown in the portal header and email footer.">
            <input
              type="text"
              value={settings.orgName}
              onChange={(e) => set("orgName", e.target.value)}
              placeholder="Acme Manufacturing GmbH"
              className={inputCls}
            />
          </Field>
          <Field label="Logo URL" hint="Direct link to your logo image (PNG or SVG, min 48px tall).">
            <input
              type="url"
              value={settings.logoUrl}
              onChange={(e) => set("logoUrl", e.target.value)}
              placeholder="https://yourcompany.com/logo.png"
              className={inputCls}
            />
            {settings.logoUrl && (
              <img
                src={settings.logoUrl}
                alt="Logo preview"
                className="mt-2 h-10 rounded object-contain"
                onError={(e) => ((e.target as HTMLImageElement).style.display = "none")}
              />
            )}
          </Field>
          <Field label="Brand colour" hint="Used for buttons and accents on the supplier portal.">
            <div className="flex items-center gap-3">
              <input
                type="color"
                value={settings.brandColor}
                onChange={(e) => set("brandColor", e.target.value)}
                className="h-9 w-16 cursor-pointer rounded-lg border border-[#DCDCE0] p-0.5"
              />
              <input
                type="text"
                value={settings.brandColor}
                onChange={(e) => set("brandColor", e.target.value)}
                className={`${inputCls} flex-1 font-mono`}
              />
            </div>
          </Field>
        </Section>

        {/* ── SAP connector ─────────────────────────────────────────────── */}
        <Section title="SAP OData connector" description="Connect directly to your SAP system to pull material master data. Supports S/4HANA and ECC.">
          <Field label="SAP hostname" hint="e.g. https://your-sap-system.company.com or https://mysap.company.com:8000">
            <input
              type="url"
              value={settings.sapHost}
              onChange={(e) => set("sapHost", e.target.value)}
              placeholder="https://your-sap.company.com"
              className={inputCls}
            />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="SAP Client" hint="Usually 100, 200, or 300">
              <input
                type="text"
                value={settings.sapClient}
                onChange={(e) => set("sapClient", e.target.value)}
                placeholder="100"
                className={inputCls}
              />
            </Field>
            <Field label="Username" hint="SAP dialog user with MM read access">
              <input
                type="text"
                value={settings.sapUsername}
                onChange={(e) => set("sapUsername", e.target.value)}
                placeholder="MIA_READ"
                className={inputCls}
              />
            </Field>
          </div>
          <Field label="Password" hint="Stored only in your browser — never sent to MIA servers.">
            <input
              type="password"
              value={settings.sapPassword}
              onChange={(e) => set("sapPassword", e.target.value)}
              placeholder="••••••••"
              className={inputCls}
            />
          </Field>

          {/* Test connection */}
          <div className="flex items-center gap-3 rounded-xl border border-[#DCDCE0] bg-[#F5F5F7] p-3.5">
            <input
              type="text"
              value={testMaterial}
              onChange={(e) => setTestMaterial(e.target.value)}
              placeholder="Material number to test (e.g. 1000023)"
              className="flex-1 bg-transparent text-[13px] focus:outline-none"
            />
            <button
              onClick={testSap}
              disabled={sapTesting || !settings.sapHost || !testMaterial.trim()}
              className="shrink-0 rounded-xl bg-[#17181A] px-3.5 py-2 text-[12px] font-medium text-white transition-opacity hover:opacity-85 disabled:opacity-30"
            >
              {sapTesting ? "Testing..." : "Test connection"}
            </button>
          </div>

          {sapStatus === "ok" && (
            <p className="text-[13px] text-[#1B8A5A]">
              SAP connection successful — material data fetched.
            </p>
          )}
          {sapStatus === "error" && (
            <p className="text-[13px] text-[#B8760B]">{sapError}</p>
          )}

          <p className="text-[12px] text-[#6E6E73]">
            To use SAP in the workspace, click &ldquo;Fetch from SAP&rdquo; and enter a material number.
            MIA will pull MARA/MARC data via OData and map it automatically.
          </p>
        </Section>

        {/* Save */}
        <div className="flex items-center gap-3">
          <button
            onClick={save}
            className="rounded-full bg-[#17181A] px-6 py-2.5 text-[14px] font-semibold text-white transition-opacity hover:opacity-85"
          >
            Save settings
          </button>
          {saved && (
            <span className="text-[13px] text-[#1B8A5A]">Saved</span>
          )}
        </div>
      </div>
    </div>
  );
}

const inputCls =
  "w-full rounded-xl border border-[#DCDCE0] bg-white px-3.5 py-2.5 text-[14px] text-[#17181A] placeholder:text-[#6E6E73] focus:border-[#0B5FD0] focus:outline-none";

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-[#DCDCE0] bg-white p-6 space-y-5">
      <div>
        <h2 className="text-[16px] font-semibold text-[#17181A]">{title}</h2>
        <p className="mt-1 text-[13px] text-[#6E6E73]">{description}</p>
      </div>
      {children}
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label className="block text-[13px] font-medium text-[#17181A]">{label}</label>
      <p className="text-[12px] text-[#6E6E73]">{hint}</p>
      {children}
    </div>
  );
}
