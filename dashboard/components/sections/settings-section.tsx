"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import ProxiesSection from "@/components/proxies-section";
import { AccountTable } from "@/components/reddit/account-table";
import SubredditSection from "@/components/sections/subreddits-section";
import { activeTab, DashboardTabs, type DashboardTab } from "@/components/sections/dashboard-tabs";

const TABS: DashboardTab[] = [
  {
    key: "accounts",
    label: "Accounts",
    description: "Manage posting accounts, health, and limits.",
  },
  {
    key: "subreddits",
    label: "Subreddits",
    description: "Choose which communities are tracked and scraped.",
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
      {tab.key === "subreddits" && (
        <Suspense>
          <SubredditSection />
        </Suspense>
      )}
      {tab.key === "accounts" && <AccountTable />}
      {tab.key === "proxies" && <ProxiesSection />}
    </div>
  );
}
