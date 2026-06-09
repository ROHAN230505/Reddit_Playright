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
    <div className="rounded-lg border border-border bg-white p-2 shadow-soft">
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
                  ? "bg-slate-900 text-white shadow-sm"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-950",
              )}
            >
              {tab.label}
            </Link>
          );
        })}
      </div>
      <div className="px-1 pt-2 text-xs text-muted">{selected.description}</div>
    </div>
  );
}
