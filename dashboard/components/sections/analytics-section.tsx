"use client";

import { useEffect, useState } from "react";
import { api, type DashboardSummary } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Card, Skeleton } from "@/components/legacy-ui";
import { EmptyState } from "@/components/sections/shared";

export default function AnalyticsSection() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);

  useEffect(() => {
    api.summary().then(setSummary).catch(() => {});
    const timer = window.setInterval(() => {
      api.summary().then(setSummary).catch(() => {});
    }, 15000);
    return () => window.clearInterval(timer);
  }, []);

  const promo = summary?.promo_replies || 0;
  const normal = summary?.normal_replies || 0;
  const total = promo + normal;

  return (
    <div className="grid gap-5 xl:grid-cols-[1fr_420px]">
      <Card className="min-w-0 p-4">
        <h2 className="text-lg font-semibold">Analytics</h2>
        {summary ? (
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <RatioBar
              label="sentx.ai promotional replies"
              value={promo}
              total={total}
              className="bg-amber-500"
            />
            <RatioBar
              label="Normal replies"
              value={normal}
              total={total}
              className="bg-teal-600"
            />
            <RatioBar
              label="Pending replies"
              value={summary.reply_counts?.PENDING || 0}
              total={Math.max(1, total)}
              className="bg-slate-800"
            />
            <RatioBar
              label="Done replies"
              value={summary.reply_counts?.DONE || 0}
              total={Math.max(1, total)}
              className="bg-green-600"
            />
          </div>
        ) : (
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
          </div>
        )}
      </Card>
      <Card className="min-w-0 p-4">
        <h2 className="text-lg font-semibold">Latest Errors</h2>
        <div className="mt-3 max-h-[660px] space-y-2 overflow-y-auto pr-1">
          {(summary?.latest_scrape_errors || []).map((run) => (
            <div key={run.id} className="min-w-0 rounded-md border border-red-100 bg-red-50 p-3 text-sm">
              <div className="font-medium">
                r/{run.subreddit} - {formatDate(run.created_at)}
              </div>
              <div className="mt-1 max-w-full overflow-hidden break-words text-danger">
                {run.error_message}
              </div>
            </div>
          ))}
          {!summary?.latest_scrape_errors?.length && (
            <EmptyState
              title="No scrape errors"
              description="Recent scrape runs have not recorded errors."
              compact
            />
          )}
        </div>
      </Card>
    </div>
  );
}

function RatioBar({
  label,
  value,
  total,
  className,
}: {
  label: string;
  value: number;
  total: number;
  className: string;
}) {
  const width = total ? Math.round((value / total) * 100) : 0;
  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-sm">
        <span className="font-medium">{label}</span>
        <span className="text-muted">{value}</span>
      </div>
      <div className="h-3 rounded-full bg-slate-100">
        <div className={`h-3 rounded-full ${className}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}
