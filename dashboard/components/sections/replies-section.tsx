"use client";

import { useEffect, useState } from "react";
import { api, type ReplySummary } from "@/lib/api";
import { Skeleton, StateMessage } from "@/components/ui";
import { RepliesTabs } from "@/components/sections/shared";
import { RecentlyPostedPanel } from "@/components/recently-posted";
import { PostedAnalytics } from "@/components/posted-analytics";

export default function RepliesSection() {
  const [posted, setPosted] = useState<ReplySummary[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const load = () => {
      // Reddit-only, full set (capped at the backend max of 2000) so the
      // analytics windows are accurate rather than truncated. The summary
      // projection skips the heavy comment/post text this view never reads,
      // so the payload is ~7x smaller and the page paints far sooner.
      api
        .repliesSummary("POSTED", 2000, "reddit")
        .then((rows) => {
          if (active) {
            setPosted(rows);
            setError("");
          }
        })
        .catch((err) => {
          if (active) {
            setPosted([]);
            setError(err instanceof Error ? err.message : "Could not load Reddit posted replies.");
          }
        });
    };
    load();
    const timer = window.setInterval(load, 30000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  if (posted === null) {
    return (
      <div className="space-y-5">
        <RepliesTabs />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24" />)}
        </div>
        <Skeleton className="h-48" />
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-48" />
          <Skeleton className="h-48" />
        </div>
        <Skeleton className="h-64" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <RepliesTabs />
      {error && (
        <StateMessage title="Could not load Reddit replies" description={error} tone="error" compact />
      )}
      {!error && posted.length === 0 && (
        <StateMessage title="No posted Reddit replies yet" description="Posted replies will appear here after successful posting." />
      )}
      <PostedAnalytics posted={posted} groupLabel="Top subreddits" groupMode="subreddit" barClass="bg-orange-400" />
      <RecentlyPostedPanel posted={posted} subtitle="Reddit · newest first" />
    </div>
  );
}
