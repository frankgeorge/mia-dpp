"use client";

import { useState } from "react";

const DATA_OPTIONS = [
  { id: "sap", label: "SAP / ERP system" },
  { id: "excel", label: "Excel or CSV files" },
  { id: "pdf", label: "PDF datasheets" },
  { id: "cad", label: "SolidWorks or CAD system" },
  { id: "website", label: "Product website" },
  { id: "unsure", label: "Not sure yet" },
];

export const COMPANY_STORAGE_KEY = "mia.company.v1";

export interface CompanyProfile {
  name: string;
  website: string;
  description: string;
}

export function getCompanyProfile(): CompanyProfile | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(COMPANY_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as CompanyProfile) : null;
  } catch {
    return null;
  }
}

interface Props {
  onClose: () => void;
}

export function OnboardingModal({ onClose }: Props) {
  const [step, setStep] = useState(1);
  const [companyName, setCompanyName] = useState("");
  const [companyWebsite, setCompanyWebsite] = useState("");
  const [productDescription, setProductDescription] = useState("");
  const [selectedSources, setSelectedSources] = useState<string[]>([]);

  function toggleSource(id: string) {
    setSelectedSources((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]
    );
  }

  function finish() {
    if (typeof window !== "undefined") {
      const profile: CompanyProfile = {
        name: companyName.trim(),
        website: companyWebsite.trim(),
        description: productDescription.trim(),
      };
      localStorage.setItem(COMPANY_STORAGE_KEY, JSON.stringify(profile));
      localStorage.setItem("mia.onboarded.v1", "1");
    }
    onClose();
  }

  const selectedLabels = DATA_OPTIONS.filter((o) => selectedSources.includes(o.id)).map((o) => o.label);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 backdrop-blur-sm">
      <div className="w-full max-w-lg animate-rise rounded-2xl bg-paper p-8 shadow-2xl">
        {/* Step dots */}
        <div className="mb-6 flex items-center justify-center gap-2">
          {[1, 2, 3].map((s) => (
            <span
              key={s}
              className={`h-2 rounded-full transition-all ${
                s === step
                  ? "w-5 bg-ink"
                  : s < step
                  ? "w-2 bg-ink/40"
                  : "w-2 bg-hairline"
              }`}
            />
          ))}
        </div>

        {/* Step 1 — Company identity */}
        {step === 1 && (
          <div>
            <h2 className="text-[22px] font-semibold tracking-tight text-ink">
              Welcome to MIA
            </h2>
            <p className="mt-2 text-[14px] text-muted">
              Tell us about your company so MIA knows who it&rsquo;s creating passports for.
            </p>
            <div className="mt-6 space-y-4">
              <div>
                <label className="mb-1.5 block text-[13px] font-medium text-ink">
                  Company name <span className="text-signal">*</span>
                </label>
                <input
                  type="text"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  placeholder="e.g. AFRISO GmbH"
                  className="w-full rounded-xl border border-hairline bg-mist px-4 py-3 text-[14px] text-ink placeholder:text-muted focus:border-signal/50 focus:outline-none focus:ring-4 focus:ring-signal/10"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-[13px] font-medium text-ink">
                  Company website
                  <span className="ml-2 text-[12px] font-normal text-muted">(optional — helps MIA skip web searches)</span>
                </label>
                <input
                  type="url"
                  value={companyWebsite}
                  onChange={(e) => setCompanyWebsite(e.target.value)}
                  placeholder="https://
                  className="w-full rounded-xl border border-hairline bg-mist px-4 py-3 text-[14px] text-ink placeholder:text-muted focus:border-signal/50 focus:outline-none focus:ring-4 focus:ring-signal/10"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-[13px] font-medium text-ink">
                  What does your company make?
                </label>
                <textarea
                  value={productDescription}
                  onChange={(e) => setProductDescription(e.target.value)}
                  rows={2}
                  placeholder="e.g. pressure sensors and measurement instruments"
                  className="w-full resize-none rounded-xl border border-hairline bg-mist px-4 py-3 text-[14px] text-ink placeholder:text-muted focus:border-signal/50 focus:outline-none focus:ring-4 focus:ring-signal/10"
                />
              </div>
            </div>
            <div className="mt-6 flex justify-end">
              <button
                onClick={() => setStep(2)}
                disabled={!companyName.trim()}
                className="rounded-full bg-ink px-6 py-2.5 text-[14px] font-medium text-white transition-all hover:-translate-y-px hover:shadow-md disabled:opacity-40"
              >
                Next
                <span className="ml-1.5">&#x2192;</span>
              </button>
            </div>
          </div>
        )}

        {/* Step 2 — Data sources */}
        {step === 2 && (
          <div>
            <h2 className="text-[22px] font-semibold tracking-tight text-ink">
              Where is your product data?
            </h2>
            <p className="mt-2 text-[14px] text-muted">
              Tick all that apply.
            </p>
            <div className="mt-5 grid grid-cols-2 gap-2.5">
              {DATA_OPTIONS.map((option) => {
                const checked = selectedSources.includes(option.id);
                return (
                  <button
                    key={option.id}
                    onClick={() => toggleSource(option.id)}
                    className={`flex items-center gap-3 rounded-xl border px-4 py-3 text-left text-[13px] font-medium transition-all ${
                      checked
                        ? "border-signal/30 bg-signalDim text-signal"
                        : "border-hairline bg-mist text-ink hover:border-signal/20 hover:bg-signalDim/50"
                    }`}
                  >
                    <span
                      className={`grid h-4 w-4 shrink-0 place-items-center rounded border transition-colors ${
                        checked ? "border-signal bg-signal" : "border-muted/40 bg-paper"
                      }`}
                    >
                      {checked && (
                        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                          <path
                            d="M2 5l2.5 2.5L8 3"
                            stroke="white"
                            strokeWidth="1.5"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      )}
                    </span>
                    {option.label}
                  </button>
                );
              })}
            </div>
            <div className="mt-6 flex items-center justify-between">
              <button
                onClick={() => setStep(1)}
                className="rounded-full border border-hairline px-5 py-2.5 text-[13px] font-medium text-muted transition-colors hover:text-ink"
              >
                <span className="mr-1.5">&#x2190;</span>
                Back
              </button>
              <button
                onClick={() => setStep(3)}
                className="rounded-full bg-ink px-6 py-2.5 text-[14px] font-medium text-white transition-all hover:-translate-y-px hover:shadow-md"
              >
                Next
                <span className="ml-1.5">&#x2192;</span>
              </button>
            </div>
          </div>
        )}

        {/* Step 3 — Confirmation */}
        {step === 3 && (
          <div>
            <div className="mb-4 grid h-12 w-12 place-items-center rounded-full bg-ok/10">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#1B8A5A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </div>
            <h2 className="text-[22px] font-semibold tracking-tight text-ink">
              MIA is ready to help
            </h2>
            <div className="mt-3 space-y-1">
              {companyName && (
                <p className="text-[14px] text-muted">
                  Company: <span className="font-medium text-ink">{companyName}</span>
                </p>
              )}
              {companyWebsite && (
                <p className="text-[14px] text-muted">
                  Website: <span className="font-medium text-ink">{companyWebsite}</span>
                </p>
              )}
              {productDescription && (
                <p className="text-[14px] text-muted">
                  Products: <span className="text-ink">{productDescription}</span>
                </p>
              )}
            </div>
            {selectedLabels.length > 0 && (
              <div className="mt-4">
                <p className="text-[13px] font-medium text-muted">Data sources:</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {selectedLabels.map((label) => (
                    <span
                      key={label}
                      className="rounded-full border border-ok/20 bg-ok/5 px-3 py-1 text-[12px] font-medium text-ok"
                    >
                      {label}
                    </span>
                  ))}
                </div>
              </div>
            )}
            <p className="mt-5 text-[13px] leading-relaxed text-muted">
              MIA will use this to skip company searches and go straight to extracting product specs and mapping DPP fields.
            </p>
            <div className="mt-6 flex items-center justify-between">
              <button
                onClick={() => setStep(2)}
                className="rounded-full border border-hairline px-5 py-2.5 text-[13px] font-medium text-muted transition-colors hover:text-ink"
              >
                <span className="mr-1.5">&#x2190;</span>
                Back
              </button>
              <button
                onClick={finish}
                className="rounded-full bg-ink px-6 py-2.5 text-[14px] font-medium text-white transition-all hover:-translate-y-px hover:shadow-md"
              >
                Open workspace
                <span className="ml-1.5">&#x2192;</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
