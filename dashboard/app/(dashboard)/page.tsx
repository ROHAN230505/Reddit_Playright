"use client";

import Link from "next/link";
import { useQueries, useQuery } from "@tanstack/react-query";
import { api, type Platform, type ReplySummary } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { PLATFORMS } from "@/components/platforms";
import { ArrowRightIcon } from "@/components/icons";
import { RecentlyPostedPanel } from "@/components/recently-posted";
import { queryKeys } from "@/lib/query-keys";
import { visibleRefetchInterval } from "@/lib/query";

const OVERVIEW_PLATFORMS = PLATFORMS.filter((item) => item.platform !== "instagram");

export default function HomePage() {
  const pendingQueries = useQueries({
    queries: OVERVIEW_PLATFORMS.map((card) => ({
      queryKey: queryKeys.workerQueue(card.platform),
      queryFn: () => api.workerQueue(card.platform),
      refetchInterval: visibleRefetchInterval(30_000),
      refetchIntervalInBackground: false,
      placeholderData: (previous: { counts: Record<string, number> } | undefined) => previous,
    })),
  });

  const postedQuery = useQuery({
    queryKey: queryKeys.repliesSummary("POSTED"),
    queryFn: () => api.repliesSummary("POSTED", 50),
    refetchInterval: visibleRefetchInterval(30_000),
    refetchIntervalInBackground: false,
    placeholderData: (previous: ReplySummary[] | undefined) => previous,
  });

  const pending: Partial<Record<Platform, number | null>> = {};
  OVERVIEW_PLATFORMS.forEach((card, index) => {
    const query = pendingQueries[index];
    if (!query || query.isError || (query.isPending && !query.data)) {
      pending[card.platform] = null;
    } else {
      pending[card.platform] = query.data?.counts?.PENDING ?? 0;
    }
  });

  const posted = postedQuery.data ?? [];

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {PLATFORMS.map((card) => {
        const count = pending[card.platform];
        const display = card.platform === "instagram" ? "Open" : count == null ? null : String(count);
        return (
          <Link key={card.href} href={card.href} className="group block">
            <Card className="flex h-full flex-col justify-between gap-6 p-5 transition-all duration-200 group-hover:-translate-y-0.5 group-hover:border-primary/40 group-hover:shadow-lift">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <span
                    className={cn(
                      "flex h-11 w-11 items-center justify-center rounded-xl ring-1 ring-inset",
                      card.chipBg,
                      card.chipText,
                      card.chipRing,
                    )}
                  >
                    <card.Icon className="h-5 w-5" />
                  </span>
                  <div>
                    <div className="text-base font-semibold tracking-tight text-foreground">{card.label}</div>
                    <div className="text-xs text-muted-foreground">{card.blurb}</div>
                  </div>
                </div>
                <ArrowRightIcon className="h-5 w-5 text-muted-foreground transition group-hover:translate-x-0.5 group-hover:text-foreground" />
              </div>
              <div>
                {display === null ? (
                  <Skeleton className="h-10 w-20" />
                ) : card.platform === "instagram" ? (
                  <div className="text-3xl font-semibold tracking-tight text-foreground">{display}</div>
                ) : (
                  <div className="text-4xl font-semibold tracking-tight text-foreground">{display}</div>
                )}
                <div className="mt-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {card.platform === "instagram" ? "Native dashboard" : "Pending replies"}
                </div>
              </div>
            </Card>
          </Link>
        );
        })}
      </div>

      <RecentlyPostedPanel posted={posted} subtitle="All platforms · newest first" />
    </div>
  );
}
