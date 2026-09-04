"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button, StateMessage } from "@/components/legacy-ui";

export function RepliesTabs() {
  const pathname = usePathname() ?? "";
  const tabs = [
    { href: "/replies", label: "Posted", active: pathname === "/replies" },
    { href: "/replies/live", label: "Live", active: pathname.startsWith("/replies/live") },
  ];
  return (
    <div className="inline-flex rounded-lg border border-slate-200 bg-white p-0.5">
      {tabs.map((tab) => (
        <Link
          key={tab.href}
          href={tab.href}
          className={`rounded-md px-3 py-1 text-sm font-medium transition ${
            tab.active ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100"
          }`}
        >
          {tab.label}
        </Link>
      ))}
    </div>
  );
}

export function EmptyState({ title, description, compact }: { title: string; description: string; compact?: boolean }) {
  return <StateMessage title={title} description={description} compact={compact} />;
}

export function Pagination({ page, totalPages, total, onPage }: { page: number; totalPages: number; total: number; onPage: (value: number) => void }) {
  return (
    <div className="mt-4 flex flex-col gap-2 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="text-sm text-muted">Page {page} of {totalPages} - {total} total</div>
      <div className="flex gap-2">
        <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button>
        <Button size="sm" variant="secondary" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>Next</Button>
      </div>
    </div>
  );
}
