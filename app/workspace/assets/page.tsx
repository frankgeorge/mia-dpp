import Link from "next/link";

export default function AssetsPage() {
  // Static empty state — will be populated from DB later
  const assets: never[] = [];

  return (
    <div className="px-8 py-8">
      <div className="mx-auto max-w-shell">
        {/* Page header */}
        <div className="mb-8 flex items-center justify-between">
          <h1 className="text-[22px] font-semibold tracking-tight text-ink">
            My Assets
          </h1>
          <Link
            href="/workspace"
            className="flex items-center gap-2 rounded-full bg-ink px-4 py-2 text-[13px] font-medium text-white transition-all hover:-translate-y-px hover:shadow-md"
          >
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
              <path d="M6.5 1v11M1 6.5h11" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
            New passport
          </Link>
        </div>

        {assets.length === 0 ? (
          <div className="flex min-h-[400px] items-center justify-center rounded-2xl border border-hairline bg-paper">
            <div className="text-center px-8 py-12 max-w-xs">
              <div className="mx-auto mb-5 grid h-14 w-14 place-items-center rounded-2xl border border-hairline bg-mist text-muted">
                <svg
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <polyline points="10 9 9 9 8 9" />
                </svg>
              </div>
              <p className="text-[16px] font-semibold text-ink">No passports yet</p>
              <p className="mt-2 text-[13px] leading-relaxed text-muted">
                Start a new chat to create your first Digital Product Passport.
              </p>
              <Link
                href="/workspace"
                className="mt-5 inline-flex items-center gap-2 rounded-full bg-ink px-5 py-2.5 text-[13px] font-medium text-white transition-all hover:-translate-y-px hover:shadow-md"
              >
                Start now
              </Link>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
