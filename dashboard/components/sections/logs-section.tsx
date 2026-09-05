"use client";

import { useEffect, useState } from "react";
import { api, type ScrapeRunList } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import {
  Badge,
  Card,
  SectionHeader,
  TableShell,
  tableCellClassName,
  tableHeadClassName,
  tableRowClassName,
} from "@/components/legacy-ui";
import { useSelectedSubreddit } from "@/lib/hooks/use-selected-subreddit";
import { EmptyState, Pagination } from "@/components/sections/shared";

export default function LogsSection() {
  const [selectedSubreddit] = useSelectedSubreddit();
  const [scrapeRuns, setScrapeRuns] = useState<ScrapeRunList | null>(null);
  const [summary, setSummary] = useState<{ counts: Record<string, number> } | null>(null);
  const [page, setPage] = useState(1);

  async function load() {
    const [runs, sum] = await Promise.all([
      api.scrapeRuns(page, 8, selectedSubreddit || undefined),
      api.workerQueue("reddit"),
    ]);
    setScrapeRuns(runs);
    setSummary(sum);
  }

  useEffect(() => {
    load().catch(() => {});
    const timer = window.setInterval(() => {
      load().catch(() => {});
    }, 30_000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, selectedSubreddit]);

  const workerCounts = summary?.counts || {};
  const totalPages = Math.max(1, Math.ceil((scrapeRuns?.total_runs || 0) / (scrapeRuns?.page_size || 8)));

  return (
    <div className="space-y-5">
      <Card className="p-4">
        <SectionHeader title="Worker Status" description="Current posting queue counts by state." />
        <div className="mt-3 grid gap-3 sm:grid-cols-4">
          {["APPROVED", "POSTING", "POSTED", "FAILED"].map((status) => (
            <div key={status} className="rounded-md border border-border bg-card p-3">
              <div className="text-xs font-semibold text-muted-foreground">{status}</div>
              <div className="mt-1 text-2xl font-semibold">{workerCounts[status] || 0}</div>
            </div>
          ))}
        </div>
      </Card>
      <Card className="overflow-hidden">
        <div className="border-b border-border p-4">
          <h2 className="text-lg font-semibold">Live Scrape Logs</h2>
          <p className="text-sm text-muted-foreground">
            Polling recent scrape run records, status, counts, and errors.
          </p>
        </div>
        <TableShell minWidth={820}>
            <thead className={tableHeadClassName}>
              <tr>
                <th className={tableCellClassName}>Subreddit</th>
                <th className={tableCellClassName}>Status</th>
                <th className={tableCellClassName}>Source</th>
                <th className={tableCellClassName}>Counts</th>
                <th className={tableCellClassName}>Started</th>
                <th className={tableCellClassName}>Finished</th>
                <th className={tableCellClassName}>Error</th>
              </tr>
            </thead>
            <tbody>
              {(scrapeRuns?.runs || []).map((run) => (
                <tr key={run.id} className={tableRowClassName}>
                  <td className={`${tableCellClassName} font-medium`}>r/{run.subreddit}</td>
                  <td className={tableCellClassName}>
                    <Badge>{run.status}</Badge>
                  </td>
                  <td className={tableCellClassName}>{run.source}</td>
                  <td className={tableCellClassName}>
                    {run.posts_count} posts - {run.comments_count} comments - {run.replies_count}{" "}
                    replies
                  </td>
                  <td className={tableCellClassName}>{formatDate(run.created_at)}</td>
                  <td className={tableCellClassName}>{formatDate(run.finished_at)}</td>
                  <td className={`${tableCellClassName} text-danger`}>{run.error_message || ""}</td>
                </tr>
              ))}
            </tbody>
        </TableShell>
        {!scrapeRuns?.runs?.length && (
          <div className="p-4">
            <EmptyState
              title="No scrape logs"
              description="Scrape runs will appear here after jobs are queued or completed."
            />
          </div>
        )}
        <Pagination
          page={page}
          totalPages={totalPages}
          total={scrapeRuns?.total_runs || 0}
          onPage={setPage}
        />
      </Card>
    </div>
  );
}
