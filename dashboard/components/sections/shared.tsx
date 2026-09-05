"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import { StateMessage } from "@/components/legacy-ui";

function PillTabs({ tabs }: { tabs: { href: string; label: string; active: boolean }[] }) {
  return (
    <div className="inline-flex rounded-lg border border-border bg-card p-0.5">
      {tabs.map((tab) => (
        <Link
          key={tab.href}
          href={tab.href}
          className={`rounded-md px-3 py-1 text-sm font-medium transition ${
            tab.active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"
          }`}
        >
          {tab.label}
        </Link>
      ))}
    </div>
  );
}

export function RepliesTabs() {
  const pathname = usePathname() ?? "";
  return (
    <PillTabs
      tabs={[
        { href: "/replies", label: "Posted", active: pathname === "/replies" },
        { href: "/replies/live", label: "Live", active: pathname.startsWith("/replies/live") },
      ]}
    />
  );
}

export function GodlikeTabs() {
  const pathname = usePathname() ?? "";
  return (
    <PillTabs
      tabs={[
        { href: "/godlike", label: "Posted", active: pathname === "/godlike" },
        { href: "/godlike/live", label: "Live", active: pathname.startsWith("/godlike/live") },
      ]}
    />
  );
}

export function EmptyState({ title, description, compact }: { title: string; description: string; compact?: boolean }) {
  return <StateMessage title={title} description={description} compact={compact} />;
}

export function Pagination({ page, totalPages, total, onPage }: { page: number; totalPages: number; total: number; onPage: (value: number) => void }) {
  return (
    <div className="mt-4 flex flex-col gap-2 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="text-sm text-muted-foreground">Page {page} of {totalPages} - {total} total</div>
      <div className="flex gap-2">
        <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button>
        <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>Next</Button>
      </div>
    </div>
  );
}
