"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { visibleRefetchInterval } from "@/lib/query";
import { formatDate } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/sections/shared";

const QUEUE_STATUSES = ["PENDING", "APPROVED", "POSTING", "POSTED", "FAILED"] as const;

export default function AnalyticsSection() {
  const { data: summary } = useQuery({
    queryKey: queryKeys.dashboardSummary(),
    queryFn: () => api.summary(),
    refetchInterval: visibleRefetchInterval(30_000),
    refetchIntervalInBackground: false,
    placeholderData: (previous) => previous,
  });

  const promo = summary?.promo_replies || 0;
  const normal = summary?.normal_replies || 0;
  const total = promo + normal;
  const workerCounts = summary?.worker_counts ?? {};

  return (
    <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(16rem,22rem)]">
      <Card className="min-w-0 p-4">
        <h2 className="text-lg font-semibold text-foreground">Analytics</h2>
        {summary ? (
          <>
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <RatioBar
                label="Promo replies"
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
                className="bg-foreground/70"
              />
              <RatioBar
                label="Done replies"
                value={summary.reply_counts?.DONE || 0}
                total={Math.max(1, total)}
                className="bg-green-600"
              />
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              <Fact label="Tracked subs" value={formatCount(summary.total_subreddits)} />
              <Fact label="Posts scraped" value={formatCount(summary.total_posts)} />
              <Fact label="Comments" value={formatCount(summary.total_comments)} />
              <Fact label="Promo mix" value={`${Math.round((summary.promo_ratio || 0) * 100)}%`} />
              <Fact
                label="Last scrape"
                value={summary.latest_scrape_time ? formatDate(summary.latest_scrape_time) : "n/a"}
              />
              <Fact
                label="Posting now"
                value={formatCount(workerCounts.POSTING || 0)}
              />
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {QUEUE_STATUSES.map((status) => (
                <span
                  key={status}
                  className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/40 px-2 py-1 font-mono text-[11px] text-muted-foreground"
                >
                  <span className="uppercase">{status}</span>
                  <span className="font-semibold text-foreground">
                    {formatCount(workerCounts[status] || 0)}
                  </span>
                </span>
              ))}
            </div>
          </>
        ) : (
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
          </div>
        )}
      </Card>
      <Card className="min-w-0 p-4">
        <h2 className="text-lg font-semibold text-foreground">Latest Errors</h2>
        <div className="mt-3 max-h-80 space-y-2 overflow-y-auto pr-1">
          {(summary?.latest_scrape_errors || []).map((run) => (
            <div key={run.id} className="min-w-0 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm">
              <div className="font-medium text-foreground">
                r/{run.subreddit} - {formatDate(run.created_at)}
              </div>
              <div className="mt-1 max-w-full overflow-hidden break-words text-destructive">
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

function formatCount(value: number) {
  return value.toLocaleString();
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border/80 bg-muted/30 px-3 py-2">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 truncate text-sm font-medium text-foreground">{value}</div>
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
        <span className="font-medium text-foreground">{label}</span>
        <span className="text-muted-foreground">{value.toLocaleString()}</span>
      </div>
      <div className="h-3 rounded-full bg-muted">
        <div className={`h-3 rounded-full ${className}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}
