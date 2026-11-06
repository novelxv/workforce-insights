"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Suspense, useState, type ReactNode } from "react";

import { api } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/format";
import { useMe } from "@/lib/session";
import type { Me } from "@/lib/types";
import { MenuIcon } from "./icons";
import { Skeleton, cx } from "./ui";

const NAV: { href: string; label: string; exact?: boolean; hrOnly?: boolean }[] = [
  { href: "/", label: "Overview", exact: true },
  { href: "/ask", label: "Ask" },
  { href: "/explore", label: "Explore" },
  { href: "/retention", label: "Retention" },
  { href: "/risk", label: "Attrition risk" },
  { href: "/model", label: "Model card" },
  { href: "/definitions", label: "Definitions & exports" },
];

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2.5 px-1">
      <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden>
        <rect width="32" height="32" rx="7" fill="#3b2a5c" />
        <path d="M9 23V15M14.5 23V10M20 23v-6" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" />
        <circle cx="24" cy="10" r="2.4" fill="#c9b8ea" />
      </svg>
      <div className="leading-tight">
        <div className="text-[14px] font-semibold text-fg">Workforce Insights</div>
        <div className="text-[11px] text-fg-3">Arunika Life · synthetic data</div>
      </div>
    </Link>
  );
}

function NavLinks({ onNavigate }: { onNavigate: () => void }) {
  const pathname = usePathname();
  return (
    <nav className="flex flex-col gap-0.5">
      {NAV.map((n) => {
        const active = n.exact ? pathname === n.href : pathname.startsWith(n.href);
        return (
          <Link
            key={n.href}
            href={n.href}
            onClick={onNavigate}
            className={cx(
              "rounded-md px-2.5 py-1.5 text-[13.5px]",
              active ? "bg-ink-soft font-medium text-ink" : "text-fg-2 hover:bg-surface-3 hover:text-fg",
            )}
          >
            {n.label}
          </Link>
        );
      })}
    </nav>
  );
}

function Account({ me, onSignOut }: { me: Me; onSignOut: () => void }) {
  return (
    <div className="border-t border-line px-3 py-3">
      <div className="truncate text-[13px] font-medium text-fg">{ROLE_LABEL[me.role]}</div>
      <div className="truncate text-[12px] text-fg-3">{me.email}</div>
      <div className="mt-1.5 text-[11.5px] leading-snug text-fg-3">{me.scope}</div>
      <button onClick={onSignOut} className="mt-2 text-[12.5px] text-link hover:underline">
        Sign out
      </button>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { me, isLoading } = useMe();
  const [menuOpen, setMenuOpen] = useState(false);

  async function signOut() {
    await api.post("/auth/logout");
    router.replace("/login");
  }

  const nav = isLoading ? (
    <div className="flex flex-col gap-1">
      {Array.from({ length: 6 }).map((_, i) => (
        <Skeleton key={i} className="mx-2 my-1.5 h-5" />
      ))}
    </div>
  ) : (
    <Suspense>
      <NavLinks onNavigate={() => setMenuOpen(false)} />
    </Suspense>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[220px_1fr]">
      <aside className="hidden border-r border-line bg-surface lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col">
        <div className="px-3 py-4">
          <Brand />
        </div>
        <div className="flex-1 overflow-y-auto px-2">{nav}</div>
        {me && <Account me={me} onSignOut={signOut} />}
      </aside>
      <header className="flex items-center justify-between border-b border-line bg-surface px-4 py-3 lg:hidden">
        <Brand />
        <button
          onClick={() => setMenuOpen((v) => !v)}
          className="rounded-md p-1.5 text-fg-2 hover:bg-surface-3"
          aria-label="Menu"
          aria-expanded={menuOpen}
        >
          <MenuIcon size={20} />
        </button>
      </header>
      {menuOpen && (
        <div className="border-b border-line bg-surface px-2 pb-2 lg:hidden">
          {nav}
          {me && <Account me={me} onSignOut={signOut} />}
        </div>
      )}
      <main className="min-w-0 px-4 py-6 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[1240px]">{children}</div>
      </main>
    </div>
  );
}
