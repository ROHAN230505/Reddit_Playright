"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import AccountsSection from "@/components/accounts-section";
import ProxiesSection from "@/components/proxies-section";
import RepliesLiveSection from "@/components/sections/replies-live-section";
import SubredditSection from "@/components/sections/subreddits-section";
import { activeTab, DashboardTabs, type DashboardTab } from "@/components/sections/dashboard-tabs";

const TABS: DashboardTab[] = [
  {
    key: "queue",
    label: "Queue",
    description: "Review and manage replies ready for posting.",
  },
  {
    key: "subreddits",
    label: "Subreddits",
    description: "Choose which communities are tracked and scraped.",
  },
  {
    key: "accounts",
    label: "Accounts",
    description: "Manage posting accounts, health, and limits.",
  },
  {
    key: "proxies",
    label: "Proxies",
    description: "Manage proxy inventory and connection checks.",
  },
];

export default function SettingsSection() {
  const searchParams = useSearchParams();
  const tab = activeTab(TABS, searchParams.get("tab"));

  return (
    <div className="space-y-5">
      <DashboardTabs basePath="/settings" tabs={TABS} />
      {tab.key === "queue" && (
        <Suspense>
          <RepliesLiveSection />
        </Suspense>
      )}
      {tab.key === "subreddits" && (
        <Suspense>
          <SubredditSection />
        </Suspense>
      )}
      {tab.key === "accounts" && <AccountsSection />}
      {tab.key === "proxies" && <ProxiesSection />}
    </div>
  );
}
