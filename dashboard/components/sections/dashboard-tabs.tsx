"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { cn } from "@/lib/utils";

export type DashboardTab = {
  key: string;
  label: string;
  description: string;
};

export function activeTab(tabs: DashboardTab[], value: string | null) {
  return tabs.find((tab) => tab.key === value) ?? tabs[0];
}

export function DashboardTabs({
  basePath,
  tabs,
}: {
  basePath: string;
  tabs: DashboardTab[];
}) {
  const searchParams = useSearchParams();
  const selected = activeTab(tabs, searchParams.get("tab"));

  return (
    <div className="rounded-lg border border-border bg-card p-2 shadow-soft">
      <div className="flex gap-2 overflow-x-auto">
        {tabs.map((tab) => {
          const isSelected = tab.key === selected.key;
          return (
            <Link
              key={tab.key}
              href={`${basePath}?tab=${tab.key}`}
              className={cn(
                "min-w-fit rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isSelected
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              {tab.label}
            </Link>
          );
        })}
      </div>
      <div className="px-1 pt-2 text-xs text-muted-foreground">{selected.description}</div>
    </div>
  );
}
