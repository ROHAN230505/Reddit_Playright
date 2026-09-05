"use client";

import { useMemo, useState } from "react";
import { type ReplySummary } from "@/lib/api";
import { useVisibleInterval } from "@/lib/hooks/use-visible-interval";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

// Backend returns naive UTC datetimes (no tz suffix). JS parses those as
// LOCAL time, so "Xm ago" silently breaks for non-UTC timezones. Force UTC.
function parseServerUtc(value: string): number {
  if (/Z$/.test(value) || /[+-]\d{2}:?\d{2}$/.test(value)) {
    return new Date(value).getTime();
  }
  return new Date(value + "Z").getTime();
}

function formatTimeAgo(ms: number): string {
  const seconds = Math.max(0, Math.floor((Date.now() - ms) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ${minutes % 60}m ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ${hours % 24}h ago`;
}

function platformBadge(reply: ReplySummary) {
  if (reply.platform === "glp") {
    return { className: "bg-violet-500/15 text-violet-400", label: `glp/${reply.platform_section ?? "forum"}` };
  }
  if (reply.platform === "chan") {
    return { className: "bg-emerald-500/15 text-emerald-400", label: `/${reply.platform_section ?? reply.subreddit ?? "board"}/` };
  }
  return { className: "bg-orange-500/15 text-orange-400", label: `r/${reply.subreddit}` };
}

/**
 * Recently-posted feed. Presentational — the caller decides scope by passing
 * a pre-filtered `posted` list (e.g. reddit-only on /replies, all platforms
 * on the homepage). Sorts newest-first and shows a "View" link per item.
 */
export function RecentlyPostedPanel({
  posted,
  title = "Recently posted",
  subtitle = "Newest first",
}: {
  posted: ReplySummary[];
  title?: string;
  subtitle?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  // Tick once a minute so "Xm ago" updates without a full reload.
  const [, setTick] = useState(0);
  useVisibleInterval(() => setTick((n) => n + 1), 60_000);

  const sorted = useMemo(() => {
    const items = [...posted].filter((r) => r.posted_at);
    items.sort((a, b) => {
      const aTs = a.posted_at ? parseServerUtc(a.posted_at) : 0;
      const bTs = b.posted_at ? parseServerUtc(b.posted_at) : 0;
      return bTs - aTs;
    });
    return items;
  }, [posted]);

  const visible = expanded ? sorted.slice(0, 50) : sorted.slice(0, 10);

  return (
    <Card className="p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <div>
          <h2 className="text-sm font-semibold text-foreground">{title}</h2>
          <p className="text-xs text-muted-foreground">{subtitle} · {sorted.length} total</p>
        </div>
        {sorted.length > 10 && (
          <Button size="sm" variant="ghost" onClick={() => setExpanded((v) => !v)}>
            {expanded ? "Show 10" : `Show all (${Math.min(sorted.length, 50)})`}
          </Button>
        )}
      </div>
      {sorted.length === 0 ? (
        <p className="text-xs text-muted-foreground">No posted replies yet.</p>
      ) : (
        <ul className="divide-y divide-border">
          {visible.map((reply) => {
            const postedMs = reply.posted_at ? parseServerUtc(reply.posted_at) : null;
            const postedUrl = reply.posted_url?.trim() || null;
            const badge = platformBadge(reply);
            return (
              <li key={reply.reply_id} className="flex items-center justify-between gap-3 py-2 text-sm">
                <div className="flex min-w-0 flex-1 items-center gap-2">
                  <span className={"inline-flex shrink-0 items-center rounded px-1.5 py-0.5 font-mono text-[10px] " + badge.className}>
                    {badge.label}
                  </span>
                  <span className="truncate text-foreground" title={reply.reply_text}>
                    {reply.reply_text}
                  </span>
                </div>
                <span className="shrink-0 whitespace-nowrap text-xs text-muted-foreground">
                  {postedMs ? formatTimeAgo(postedMs) : ""}
                </span>
                <span className="w-[140px] shrink-0 text-right text-xs">
                  {postedUrl ? (
                    <a
                      href={postedUrl}
                      target="_blank"
                      rel="noreferrer noopener"
                      title="Open the posted reply"
                      className="text-primary hover:underline"
                    >
                      View ↗
                    </a>
                  ) : (
                    <span className="italic text-muted-foreground" title="No posted URL captured for this reply">
                      link not available
                    </span>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
