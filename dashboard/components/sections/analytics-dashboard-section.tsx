"use client";

import { useSearchParams } from "next/navigation";
import AnalyticsSection from "@/components/sections/analytics-section";
import FeedSection from "@/components/sections/feed-section";
import LogsSection from "@/components/sections/logs-section";
import LiveSection from "@/components/live-section";
import { activeTab, DashboardTabs, type DashboardTab } from "@/components/sections/dashboard-tabs";

const TABS: DashboardTab[] = [
  {
    key: "overview",
    label: "Overview",
    description: "High-level reply counts, promo mix, and recent errors.",
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
  {
    key: "worker",
    label: "Worker Status",
    description: "Read-only account and queue monitoring.",
  },
];

export default function AnalyticsDashboardSection() {
  const searchParams = useSearchParams();
  const tab = activeTab(TABS, searchParams.get("tab"));

  return (
    <div className="space-y-5">
      <DashboardTabs basePath="/analytics" tabs={TABS} />
      {tab.key === "overview" && <AnalyticsSection />}
      {tab.key === "feed" && <FeedSection />}
      {tab.key === "logs" && <LogsSection />}
      {tab.key === "worker" && <LiveSection onGoToAccounts={() => window.location.assign("/settings?tab=accounts")} />}
    </div>
  );
}
