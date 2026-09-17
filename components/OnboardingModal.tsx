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

interface Props {
  onClose: () => void;
}

export function OnboardingModal({ onClose }: Props) {
  const [step, setStep] = useState(1);
  const [productDescription, setProductDescription] = useState("");
  const [selectedSources, setSelectedSources] = useState<string[]>([]);

  function toggleSource(id: string) {
    setSelectedSources((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]
    );
  }

  function finish() {
    if (typeof window !== "undefined") {
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

        {/* Step 1 */}
        {step === 1 && (
          <div>
            <h2 className="text-[22px] font-semibold tracking-tight text-ink">
              Welcome to MIA
            </h2>
            <p className="mt-2 text-[14px] text-muted">
              Let&rsquo;s set up your workspace in 2 minutes.
            </p>
            <div className="mt-6">
              <label className="mb-2 block text-[13px] font-medium text-ink">
                Describe what your company makes
              </label>
              <textarea
                value={productDescription}
                onChange={(e) => setProductDescription(e.target.value)}
                rows={3}
                placeholder="e.g. electric motors for industrial pumps"
                className="w-full resize-none rounded-xl border border-hairline bg-mist px-4 py-3 text-[14px] text-ink placeholder:text-muted focus:border-signal/50 focus:outline-none focus:ring-4 focus:ring-signal/10"
              />
            </div>
            <div className="mt-6 flex justify-end">
              <button
                onClick={() => setStep(2)}
                className="rounded-full bg-ink px-6 py-2.5 text-[14px] font-medium text-white transition-all hover:-translate-y-px hover:shadow-md"
              >
                Next
                <span className="ml-1.5">&#x2192;</span>
              </button>
            </div>
          </div>
        )}

        {/* Step 2 */}
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

        {/* Step 3 */}
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
            {productDescription && (
              <p className="mt-2 text-[14px] text-muted">
                You make: <span className="text-ink">{productDescription}</span>
              </p>
            )}
            {selectedLabels.length > 0 && (
              <div className="mt-4">
                <p className="text-[13px] font-medium text-muted">Data sources you selected:</p>
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
              MIA will ask you for access to each source as it needs it. You can connect sources anytime from the Data Sources page.
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
