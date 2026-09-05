"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import AnalyticsSection from "@/components/sections/analytics-section";
import FeedSection from "@/components/sections/feed-section";
import LogsSection from "@/components/sections/logs-section";
import RedditAutomationSection from "@/components/sections/reddit-automation-section";
import RepliesSection from "@/components/sections/replies-section";
import { activeTab, DashboardTabs, type DashboardTab } from "@/components/sections/dashboard-tabs";

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
