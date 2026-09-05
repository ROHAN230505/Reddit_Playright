"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { visibleRefetchInterval } from "@/lib/query";
import { formatDate } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/sections/shared";

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

  return (
    <div className="grid gap-5 xl:grid-cols-[1fr_420px]">
      <Card className="min-w-0 p-4">
        <h2 className="text-lg font-semibold text-foreground">Analytics</h2>
        {summary ? (
          <div className="mt-5 grid gap-4 md:grid-cols-2">
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
        ) : (
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
          </div>
        )}
      </Card>
      <Card className="min-w-0 p-4">
        <h2 className="text-lg font-semibold text-foreground">Latest Errors</h2>
        <div className="mt-3 max-h-[660px] space-y-2 overflow-y-auto pr-1">
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
        <span className="text-muted-foreground">{value}</span>
      </div>
      <div className="h-3 rounded-full bg-muted">
        <div className={`h-3 rounded-full ${className}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}
