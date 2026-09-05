"use client";

import { Suspense } from "react";
import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { Skeleton } from "@/components/ui/skeleton";
import { activeTab, DashboardTabs, type DashboardTab } from "@/components/sections/dashboard-tabs";

const tabFallback = <Skeleton className="h-64 rounded-xl" />;
const ProxiesSection = dynamic(() => import("@/components/proxies-section"), {
  loading: () => tabFallback,
});
const AccountTable = dynamic(
  () => import("@/components/reddit/account-table").then((mod) => mod.AccountTable),
  { loading: () => tabFallback },
);
const BrandSection = dynamic(() => import("@/components/sections/brand-section"), {
  loading: () => tabFallback,
});
const SubredditSection = dynamic(() => import("@/components/sections/subreddits-section"), {
  loading: () => tabFallback,
});

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
  {
    key: "brand",
    label: "Brand",
    description: "Products, topics, and which subreddits each brand owns.",
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
      {tab.key === "brand" && <BrandSection />}
    </div>
  );
}
