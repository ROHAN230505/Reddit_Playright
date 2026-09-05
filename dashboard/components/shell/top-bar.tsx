"use client";

import { useEffect } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { LogOut, Menu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAccountsHealth } from "@/lib/hooks/use-accounts-health";
import { accountIsPostable, isBanned } from "@/lib/health";
import { useNotice } from "@/lib/notice-context";
import { PLATFORMS } from "@/components/platforms";

const ANALYTICS_TAB_LABELS: Record<string, string> = {
  overview: "Overview",
  "reddit-automation": "Reddit Automation",
  feed: "Feed",
  logs: "Logs",
  worker: "Worker Status",
};

const SETTINGS_TAB_LABELS: Record<string, string> = {
  queue: "Queue",
  subreddits: "Subreddits",
  accounts: "Accounts",
  proxies: "Proxies",
  brand: "Brand",
};

const REPLIES_TAB_LABELS: Record<string, string> = {
  queue: "Queue",
  realtime: "Realtime",
};

const PATH_LABELS: Record<string, string> = {
  "/": "Dashboard",
  "/replies": "Reddit",
  "/analytics": "Analytics",
  "/settings": "Settings",
  "/godlike": "Godlike",
  "/4chan": "4chan",
  "/instagram": "Instagram",
  "/live": "Realtime",
  "/feed": "Feed",
  "/logs": "Logs",
  "/accounts": "Accounts",
  "/proxies": "Proxies",
  "/subreddits": "Subreddits",
};

function pageCrumbs(pathname: string, tab: string | null): string[] {
  if (pathname === "/analytics") {
    const label = ANALYTICS_TAB_LABELS[tab || "overview"] ?? ANALYTICS_TAB_LABELS.overview;
    return ["Analytics", label];
  }
  if (pathname === "/settings") {
    const label = SETTINGS_TAB_LABELS[tab || "queue"] ?? SETTINGS_TAB_LABELS.queue;
    return ["Settings", label];
  }
  if (pathname === "/replies" || pathname.startsWith("/replies/")) {
    const crumbs = ["Reddit"];
    if (tab && REPLIES_TAB_LABELS[tab]) crumbs.push(REPLIES_TAB_LABELS[tab]);
    return crumbs;
  }

  const platform = PLATFORMS.find(
    (item) => pathname === item.href || pathname.startsWith(`${item.href}/`),
  );
  if (platform) return [platform.label];

  for (const [href, label] of Object.entries(PATH_LABELS)) {
    if (href !== "/" && (pathname === href || pathname.startsWith(`${href}/`))) {
      return [label];
    }
  }

  return [PATH_LABELS[pathname] ?? "Dashboard"];
}

async function logout() {
  await fetch("/api/login", { method: "DELETE" });
  window.location.assign("/login");
}

function openCommandPalette() {
  window.dispatchEvent(new Event("replyops:command"));
}

function HealthChip({ live }: { live: boolean }) {
  const { data } = useAccountsHealth(live);
  const accounts = data?.accounts ?? [];
  const banned = accounts.filter(isBanned).length;
  const ready = accounts.filter(accountIsPostable).length;

  if (!data) return null;

  return (
    <div className="hidden rounded-md border px-2 py-1 font-mono text-xs text-muted-foreground sm:block">
      {banned} banned · {ready} ready
    </div>
  );
}

function NoticeBanners() {
  const { notice, error } = useNotice();
  if (!notice && !error) return null;

  return (
    <div className="space-y-2 border-t px-4 py-2 md:px-6">
      {error && <p className="text-sm text-destructive">{error}</p>}
      {notice && <p className="text-sm text-muted-foreground">{notice}</p>}
    </div>
  );
}

export function TopBar({ onMenuClick }: { onMenuClick: () => void }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const tab = searchParams.get("tab");
  const crumbs = pageCrumbs(pathname, tab);
  const showHealth = pathname === "/replies" || (pathname === "/settings" && tab === "accounts");
  const liveHealth = pathname === "/replies" && tab === "realtime";

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        openCommandPalette();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <header className="sticky top-0 z-30 border-b bg-background/80 backdrop-blur">
      <div className="flex h-14 items-center justify-between gap-3 px-4 md:px-6">
        <div className="flex min-w-0 items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={onMenuClick}
            aria-label="Open navigation"
          >
            <Menu />
          </Button>
          <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-2 text-sm">
            {crumbs.map((crumb, index) => (
              <span key={`${crumb}-${index}`} className="flex min-w-0 items-center gap-2">
                {index > 0 && <span className="text-muted-foreground">/</span>}
                <span
                  className={
                    index === crumbs.length - 1
                      ? "truncate font-medium text-foreground"
                      : "truncate text-muted-foreground"
                  }
                >
                  {crumb}
                </span>
              </span>
            ))}
          </nav>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {showHealth ? <HealthChip live={liveHealth} /> : null}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="font-mono"
            onClick={openCommandPalette}
            aria-label="Open command palette"
          >
            ⌘K
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={logout} aria-label="Log out">
            <LogOut />
            <span className="hidden sm:inline">Logout</span>
          </Button>
        </div>
      </div>
      <NoticeBanners />
    </header>
  );
}
