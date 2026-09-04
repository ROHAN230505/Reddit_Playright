"use client";

import { useMemo } from "react";
import { type ReplySummary } from "@/lib/api";
import { Card } from "@/components/legacy-ui";

// Backend returns naive UTC datetimes (no tz suffix). Force UTC so the
// day-windowing is correct regardless of the viewer's timezone.
function parseServerUtc(value: string): number {
  if (/Z$/.test(value) || /[+-]\d{2}:?\d{2}$/.test(value)) {
    return new Date(value).getTime();
  }
  return new Date(value + "Z").getTime();
}

const DAY_MS = 86_400_000;

export type GroupMode = "subreddit" | "board" | "forum";

function groupName(reply: ReplySummary, mode: GroupMode): string {
  if (mode === "board") return `/${reply.platform_section ?? reply.subreddit ?? "board"}/`;
  if (mode === "forum") return `glp/${reply.platform_section ?? "forum"}`;
  return `r/${reply.subreddit || "unknown"}`;
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <Card className="p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">{value}</div>
    </Card>
  );
}

export function PostedAnalytics({
  posted,
  groupLabel,
  groupMode,
  barClass,
}: {
  posted: ReplySummary[];
  groupLabel: string;
  groupMode: GroupMode;
  barClass: string;
}) {
  const a = useMemo(() => {
    const withTs = posted.filter((p) => p.posted_at).map((p) => parseServerUtc(p.posted_at!));
    const now = Date.now();
    const sot = new Date();
    sot.setHours(0, 0, 0, 0);
    const todayStart = sot.getTime();

    const total = withTs.length;
    const today = withTs.filter((ms) => ms >= todayStart).length;
    const last7 = withTs.filter((ms) => ms >= now - 7 * DAY_MS).length;
    const last30 = withTs.filter((ms) => ms >= now - 30 * DAY_MS).length;
    const promo = posted.filter((p) => p.posted_at && p.includes_promo).length;

    const days: { label: string; full: string; count: number }[] = [];
    for (let i = 13; i >= 0; i--) {
      const d = new Date();
      d.setHours(0, 0, 0, 0);
      d.setDate(d.getDate() - i);
      const start = d.getTime();
      const end = start + DAY_MS;
      days.push({
        label: String(d.getDate()),
        full: d.toLocaleDateString(undefined, { month: "short", day: "numeric" }),
        count: withTs.filter((ms) => ms >= start && ms < end).length,
      });
    }

    const byGroup = new Map<string, number>();
    for (const p of posted) {
      if (!p.posted_at) continue;
      const k = groupName(p, groupMode);
      byGroup.set(k, (byGroup.get(k) ?? 0) + 1);
    }
    const topGroups = [...byGroup.entries()]
      .map(([name, count]) => ({ name, count }))
      .sort((x, y) => y.count - x.count)
      .slice(0, 8);

    return { total, today, last7, last30, promo, normal: total - promo, days, topGroups };
  }, [posted, groupMode]);

  const dayMax = Math.max(1, ...a.days.map((d) => d.count));
  const groupMax = Math.max(1, ...a.topGroups.map((g) => g.count));
  const promoTotal = Math.max(1, a.promo + a.normal);
  const promoPct = Math.round((a.promo / promoTotal) * 100);

  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total posted" value={a.total} />
        <StatCard label="Today" value={a.today} />
        <StatCard label="Last 7 days" value={a.last7} />
        <StatCard label="Last 30 days" value={a.last30} />
      </div>

      <Card className="p-5">
        <h2 className="text-sm font-semibold text-slate-800">Posts per day</h2>
        <p className="text-xs text-muted">Last 14 days</p>
        <div className="mt-4 flex h-32 items-end gap-1.5">
          {a.days.map((d, i) => (
            <div key={i} className="flex flex-1 flex-col items-center gap-1" title={`${d.full}: ${d.count} posted`}>
              <div className="flex w-full flex-1 items-end">
                <div
                  className={`w-full rounded-t ${barClass}`}
                  style={{ height: `${Math.round((d.count / dayMax) * 100)}%`, minHeight: d.count > 0 ? 4 : 0 }}
                />
              </div>
              <div className="text-[10px] text-muted">{d.label}</div>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <h2 className="text-sm font-semibold text-slate-800">{groupLabel}</h2>
          <p className="text-xs text-muted">By posts placed</p>
          <div className="mt-4 space-y-2">
            {a.topGroups.length === 0 && <p className="text-xs text-muted">No posts yet.</p>}
            {a.topGroups.map((g) => (
              <div key={g.name} className="flex items-center gap-3 text-sm">
                <span className="w-28 shrink-0 truncate font-mono text-xs text-slate-600" title={g.name}>
                  {g.name}
                </span>
                <div className="h-2.5 flex-1 rounded-full bg-slate-100">
                  <div className={`h-2.5 rounded-full ${barClass}`} style={{ width: `${Math.round((g.count / groupMax) * 100)}%` }} />
                </div>
                <span className="w-8 shrink-0 text-right text-xs font-medium text-slate-700">{g.count}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-5">
          <h2 className="text-sm font-semibold text-slate-800">Promo vs normal</h2>
          <p className="text-xs text-muted">Share of posts including a sentx.ai mention</p>
          <div className="mt-4 flex h-3 overflow-hidden rounded-full bg-slate-100">
            <div className="h-3 bg-amber-500" style={{ width: `${promoPct}%` }} />
            <div className="h-3 bg-teal-500" style={{ width: `${100 - promoPct}%` }} />
          </div>
          <div className="mt-3 flex items-center justify-between text-xs">
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-sm bg-amber-500" />
              Promo · {a.promo} ({promoPct}%)
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-sm bg-teal-500" />
              Normal · {a.normal}
            </span>
          </div>
        </Card>
      </div>
    </>
  );
}
