"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { UserButton } from "@clerk/nextjs";

const NAV_ITEMS = [
  {
    label: "New passport",
    href: "/workspace?new=1",
    exact: true,
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
      </svg>
    ),
  },
  {
    label: "Passports",
    href: "/workspace/assets",
    exact: false,
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </svg>
    ),
  },
];

const CONNECTOR_ITEMS = [
  {
    label: "Data Sources",
    href: "/workspace/data-sources",
    exact: false,
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <ellipse cx="12" cy="5" rx="9" ry="3" />
        <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
        <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
      </svg>
    ),
  },
  {
    label: "Agents",
    href: "/workspace/agents",
    exact: false,
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
      </svg>
    ),
  },
];

function NavItem({
  item,
  pathname,
  onClick,
}: {
  item: { label: string; href: string; exact: boolean; icon: React.ReactNode };
  pathname: string;
  onClick?: () => void;
}) {
  const hrefPath = item.href.split("?")[0];
  const isActive = item.exact
    ? pathname === hrefPath
    : pathname.startsWith(hrefPath);

  return (
    <Link
      href={item.href}
      onClick={onClick}
      className={`flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors ${
        isActive
          ? "bg-mist text-ink"
          : "text-muted hover:bg-mist/60 hover:text-ink"
      }`}
    >
      <span className="shrink-0">{item.icon}</span>
      {item.label}
    </Link>
  );
}

export function WorkspaceSidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  const close = () => setOpen(false);

  return (
    <>
      {/* Mobile hamburger — fixed, only visible on mobile */}
      <button
        onClick={() => setOpen(true)}
        className="fixed left-4 top-3.5 z-40 flex h-8 w-8 items-center justify-center rounded-lg border border-hairline bg-paper text-ink shadow-sm md:hidden"
        aria-label="Open menu"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </button>

      {/* Mobile backdrop */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[2px] md:hidden"
          onClick={close}
          aria-hidden="true"
        />
      )}

      {/* Sidebar — always visible on desktop, slides in on mobile */}
      <aside
        className={[
          "fixed left-0 top-0 z-50 flex h-full w-[240px] flex-col border-r border-hairline bg-paper",
          "transition-transform duration-200 ease-out",
          "md:translate-x-0",
          open ? "translate-x-0 shadow-xl" : "-translate-x-full md:translate-x-0",
        ].join(" ")}
      >
        {/* Logo + mobile close */}
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-hairline px-4">
          <Link href="/workspace" onClick={close} className="flex items-center gap-2.5">
            <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-ink shadow-sm">
              <span className="h-1.5 w-1.5 rounded-[1px] bg-white" />
            </span>
            <span className="text-[15px] font-semibold tracking-tight text-ink">MIA</span>
          </Link>
          <button
            onClick={close}
            className="flex h-7 w-7 items-center justify-center rounded-md text-muted hover:bg-mist hover:text-ink md:hidden"
            aria-label="Close menu"
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        {/* Nav */}
        <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-3 py-3">
          {NAV_ITEMS.map((item) => (
            <NavItem key={item.href} item={item} pathname={pathname} onClick={close} />
          ))}

          <div className="mb-1 mt-4 px-3">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted/70">
              Connectors
            </span>
          </div>
          {CONNECTOR_ITEMS.map((item) => (
            <NavItem key={item.href} item={item} pathname={pathname} onClick={close} />
          ))}
        </nav>

        {/* User area */}
        <div className="shrink-0 border-t border-hairline px-4 py-3">
          <div className="flex items-center gap-3">
            <UserButton />
            <span className="flex-1 truncate text-[13px] text-muted">Account</span>
            <Link
              href="/settings"
              onClick={close}
              title="Settings"
              className="shrink-0 rounded-md p-1.5 text-muted transition-colors hover:bg-mist hover:text-ink"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </Link>
          </div>
        </div>
      </aside>
    </>
  );
}
