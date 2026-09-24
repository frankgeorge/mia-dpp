"use client";

import { useState } from "react";

export function CopyLink({ url }: { url: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <button
      onClick={() => void copy()}
      className="rounded-full border border-hairline bg-mist px-4 py-2 text-[13px] font-medium text-ink transition-colors hover:bg-paper"
    >
      {copied ? "Copied!" : "Copy link"}
    </button>
  );
}
