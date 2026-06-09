"use client";

import { useState, Suspense, type ComponentType, type SVGProps } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { NoticeProvider, useNotice } from "@/lib/notice-context";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";
import { PLATFORMS } from "@/components/platforms";
import {
  ChartIcon,
  LayersIcon,
  LogOutIcon,
  MenuIcon,
  RefreshIcon,
  SettingsIcon,
} from "@/components/icons";

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

type NavItem = {
  href: string;
  label: string;
  subtitle: string;
  Icon: Icon;
  chipBg: string;
  chipText: string;
  chipRing: string;
  external?: boolean;
  exact?: boolean;
};

type NavSection = {
  label: string;
  items: NavItem[];
};

const platformItems: NavItem[] = PLATFORMS.map((item) => ({
  href: item.href,
  label: item.label,
  subtitle: item.blurb,
  Icon: item.Icon,
  chipBg: item.chipBg,
  chipText: item.chipText,
  chipRing: item.chipRing,
  external: item.external,
}));

const NAV_SECTIONS: NavSection[] = [
  {
    label: "Dashboard",
    items: [
      ...platformItems,
      {
        href: "/analytics",
        label: "Analytics",
        subtitle: "Performance and history",
        Icon: ChartIcon,
        chipBg: "bg-violet-50",
        chipText: "text-violet-600",
        chipRing: "ring-violet-100",
      },
      {
        href: "/settings",
        label: "Settings",
        subtitle: "Manage setup and posting",
        Icon: SettingsIcon,
        chipBg: "bg-slate-100",
        chipText: "text-slate-600",
        chipRing: "ring-slate-200",
      },
    ],
  },
];

const NAV_ITEMS = NAV_SECTIONS.flatMap((section) => section.items);

function isActive(pathname: string, item: NavItem): boolean {
  if (item.href === "/") return pathname === "/";
  if (item.exact) return pathname === item.href;
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

function currentNavItem(pathname: string): NavItem | undefined {
  return [...NAV_ITEMS]
    .filter((item) => isActive(pathname, item))
    .sort((a, b) => b.href.length - a.href.length)[0];
}

const ANALYTICS_TAB_LABELS: Record<string, string> = {
  overview: "Overview",
  feed: "Feed",
  logs: "Logs",
  worker: "Worker Status",
};

const SETTINGS_TAB_LABELS: Record<string, string> = {
  queue: "Queue",
  subreddits: "Subreddits",
  accounts: "Accounts",
  proxies: "Proxies",
};

function pageTitle(
  pathname: string,
  tab: string | null,
  fallback: NavItem | { label: string; subtitle: string },
) {
  if (pathname === "/analytics") {
    const label = ANALYTICS_TAB_LABELS[tab || "overview"] ?? ANALYTICS_TAB_LABELS.overview;
    return { label: `Analytics / ${label}`, subtitle: "Performance, history, logs, and monitoring" };
  }
  if (pathname === "/settings") {
    const label = SETTINGS_TAB_LABELS[tab || "queue"] ?? SETTINGS_TAB_LABELS.queue;
    return { label: `Settings / ${label}`, subtitle: "Manage setup and posting workflows" };
  }
  return fallback;
}

async function logout() {
  await fetch("/api/login", { method: "DELETE" });
  window.location.assign("/login");
}

function NavLink({ item, active, onClose }: { item: NavItem; active: boolean; onClose: () => void }) {
  const className = cn(
    "group flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors",
    active
      ? "bg-slate-100 text-slate-950 shadow-sm"
      : "text-slate-600 hover:bg-slate-50 hover:text-slate-950",
  );
  const inner = (
    <>
      <span
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ring-1 ring-inset",
          item.chipBg,
          item.chipText,
          item.chipRing,
        )}
      >
        <item.Icon className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1 truncate">{item.label}</span>
    </>
  );

  if (item.external) {
    return (
      <a href={item.href} target="_blank" rel="noopener noreferrer" onClick={onClose} className={className}>
        {inner}
      </a>
    );
  }

  return (
    <Link href={item.href} onClick={onClose} className={className}>
      {inner}
    </Link>
  );
}

function SidebarNav({ mobileNavOpen, onClose }: { mobileNavOpen: boolean; onClose: () => void }) {
  const pathname = usePathname();

  const nav = (
    <aside className="flex h-full min-h-0 flex-col border-r border-border bg-white">
      <Link href="/" onClick={onClose} className="flex items-center gap-3 border-b border-border px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-sm">
          <LayersIcon className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold tracking-tight text-slate-900">Reply Ops</div>
          <div className="truncate text-xs text-muted">Multi-platform console</div>
        </div>
      </Link>

      <nav className="min-h-0 flex-1 overflow-y-auto px-3 py-4">
        <div className="space-y-5">
          {NAV_SECTIONS.map((section) => (
            <div key={section.label}>
              <div className="px-2 pb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                {section.label}
              </div>
              <div className="space-y-1">
                {section.items.map((item) => (
                  <NavLink key={item.href} item={item} active={isActive(pathname, item)} onClose={onClose} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </nav>

      <div className="border-t border-border px-5 py-4">
        <div className="flex items-center gap-2 text-xs text-muted">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          Simple dashboard
        </div>
      </div>
    </aside>
  );

  return (
    <>
      <div className="hidden min-h-screen lg:block">{nav}</div>
      {mobileNavOpen && (
        <div className="fixed inset-0 z-40 bg-slate-900/40 backdrop-blur-sm lg:hidden" onClick={onClose} />
      )}
      <div
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-80 max-w-[86vw] transform shadow-xl transition-transform lg:hidden",
          mobileNavOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        {nav}
      </div>
    </>
  );
}

function DashboardHeader({ onMenuClick }: { onMenuClick: () => void }) {
  const { notice, error, busy } = useNotice();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const meta = pageTitle(
    pathname,
    searchParams.get("tab"),
    currentNavItem(pathname) ?? { label: "Dashboard", subtitle: "" },
  );

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-background/80 px-4 py-3 backdrop-blur md:px-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <Button
            variant="secondary"
            size="icon"
            className="lg:hidden"
            onClick={onMenuClick}
            aria-label="Open navigation"
          >
            <MenuIcon className="h-4 w-4" />
          </Button>
          <div className="min-w-0">
            <h1 className="truncate text-lg font-semibold tracking-tight text-slate-900 md:text-xl">
              {meta.label}
            </h1>
            {meta.subtitle && <p className="truncate text-sm text-muted">{meta.subtitle}</p>}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button variant="secondary" size="sm" onClick={() => window.location.reload()} disabled={busy}>
            <RefreshIcon className={cn("h-4 w-4", busy && "animate-spin")} />
            <span className="hidden sm:inline">Refresh</span>
          </Button>
          <Button variant="secondary" size="sm" onClick={logout}>
            <LogOutIcon className="h-4 w-4" />
            <span className="hidden sm:inline">Logout</span>
          </Button>
        </div>
      </div>
      {error && (
        <div className="mt-2 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-danger">
          {error}
        </div>
      )}
      {notice && (
        <div className="mt-2 rounded-md border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-accent">
          {notice}
        </div>
      )}
    </header>
  );
}

function DashboardShell({ children }: { children: React.ReactNode }) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <main className="min-h-screen bg-background">
      <div className="grid min-h-screen lg:grid-cols-[280px_1fr]">
        <SidebarNav mobileNavOpen={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />
        <div className="min-w-0">
          <DashboardHeader onMenuClick={() => setMobileNavOpen(true)} />
          <div className="space-y-5 p-4 md:p-6">{children}</div>
        </div>
      </div>
    </main>
  );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <NoticeProvider>
      <Suspense>
        <DashboardShell>{children}</DashboardShell>
      </Suspense>
    </NoticeProvider>
  );
}
