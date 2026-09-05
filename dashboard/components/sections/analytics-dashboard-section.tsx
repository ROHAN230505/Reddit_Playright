"use client";

import { useEffect } from "react";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { Skeleton } from "@/components/ui/skeleton";
import { activeTab, DashboardTabs, type DashboardTab } from "@/components/sections/dashboard-tabs";

const tabFallback = <Skeleton className="h-64 rounded-xl" />;
const AnalyticsSection = dynamic(() => import("@/components/sections/analytics-section"), {
  loading: () => tabFallback,
});
const FeedSection = dynamic(() => import("@/components/sections/feed-section"), {
  loading: () => tabFallback,
});
const LogsSection = dynamic(() => import("@/components/sections/logs-section"), {
  loading: () => tabFallback,
});
const RedditAutomationSection = dynamic(
  () => import("@/components/sections/reddit-automation-section"),
  { loading: () => tabFallback },
);
const RepliesSection = dynamic(() => import("@/components/sections/replies-section"), {
  loading: () => tabFallback,
});

const TABS: DashboardTab[] = [
  {
    key: "overview",
    label: "Overview",
    description: "Reply counts, posted summary, promo mix, and recent errors.",
  },
  {
    key: "reddit-automation",
    label: "Reddit Automation",
    description: "Automated Reddit posts, failures, and account cooldowns.",
  },
  {
    key: "feed",
    label: "Feed",
    description: "Fetched posts and comments from tracked sources.",
  },
  {
    key: "logs",
    label: "Logs",
    description: "Scrape history, failures, and recent status messages.",
  },
];

export default function AnalyticsDashboardSection() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedTab = searchParams.get("tab");

  useEffect(() => {
    if (requestedTab === "worker") {
      router.replace("/replies?tab=realtime");
    }
  }, [requestedTab, router]);

  if (requestedTab === "worker") {
    return null;
  }

  const tab = activeTab(TABS, requestedTab);

  return (
    <div className="space-y-5">
      <DashboardTabs basePath="/analytics" tabs={TABS} />
      {tab.key === "overview" && (
        <div className="space-y-5">
          <AnalyticsSection />
          <RepliesSection />
        </div>
      )}
      {tab.key === "reddit-automation" && <RedditAutomationSection />}
      {tab.key === "feed" && <FeedSection />}
      {tab.key === "logs" && <LogsSection />}
    </div>
  );
}
