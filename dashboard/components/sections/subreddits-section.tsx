"use client";

import { useEffect, useState } from "react";
import { api, type ScrapeRun, type SubredditHealthItem, type TrackedSubreddit } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import {
  Badge,
  Button,
  Card,
  Input,
  SectionHeader,
  StateMessage,
  TableShell,
  tableCellClassName,
  tableHeadClassName,
  tableRowClassName,
} from "@/components/ui";
import { useNotice } from "@/lib/notice-context";
import { useSelectedSubreddit } from "@/lib/hooks/use-selected-subreddit";
import { EmptyState } from "@/components/sections/shared";

export default function SubredditSection() {
  const { runAction, busy } = useNotice();
  const [selectedSubreddit, setSelectedSubreddit] = useSelectedSubreddit();
  const [subreddits, setSubreddits] = useState<TrackedSubreddit[]>([]);
  const [scrapeRuns, setScrapeRuns] = useState<ScrapeRun[]>([]);
  const [healthRows, setHealthRows] = useState<SubredditHealthItem[]>([]);
  const [query, setQuery] = useState("");
  const [newSubreddit, setNewSubreddit] = useState("");
  const [scrapeLimit, setScrapeLimit] = useState(5);
  const [loading, setLoading] = useState(true);

  async function load() {
    const [tracked, runs, nextHealthRows] = await Promise.all([
      api.trackedSubreddits(),
      api.scrapeRuns(1, 8, selectedSubreddit || undefined),
      api.subredditHealth(),
    ]);
    setSubreddits(tracked);
    setScrapeRuns(runs.runs);
    setHealthRows(nextHealthRows);
    if (!selectedSubreddit && tracked[0]) setSelectedSubreddit(tracked[0].name);
  }

  useEffect(() => {
    setLoading(true);
    load().finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filteredSubreddits = subreddits.filter((item) =>
    item.name.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <div className="grid gap-5 xl:grid-cols-[380px_1fr]">
      <Card className="p-4">
        <SectionHeader
          title="Subreddit Management"
          description="Add, scrape, and manage tracked subreddit sources."
        />
        <div className="mt-4 grid gap-3">
          <div className="flex gap-2">
            <Input
              value={newSubreddit}
              onChange={(event) => setNewSubreddit(event.target.value)}
              placeholder="Add subreddit, e.g. SaaS"
            />
            <Button
              onClick={() =>
                runAction(async () => {
                  if (!newSubreddit.trim()) return;
                  await api.addSubreddit(newSubreddit.trim());
                  setNewSubreddit("");
                  await load();
                }, "Subreddit saved")
              }
              disabled={busy || !newSubreddit.trim()}
              aria-label="Add subreddit"
            >
              Add
            </Button>
          </div>
          <div className="grid grid-cols-[1fr_110px] gap-2">
            <Input
              type="number"
              min={1}
              max={500}
              value={scrapeLimit}
              onChange={(event) => setScrapeLimit(Number(event.target.value))}
            />
            <Button
              variant="accent"
              onClick={() =>
                runAction(async () => {
                  await api.scrapeAll(scrapeLimit);
                  await load();
                }, "Queued all tracked subreddits")
              }
              disabled={busy}
            >
              Scrape All
            </Button>
          </div>
          <Button
            variant="secondary"
            onClick={() =>
              selectedSubreddit &&
              runAction(async () => {
                await api.scrapeSelected(selectedSubreddit, scrapeLimit);
                await load();
              }, `Queued r/${selectedSubreddit}`)
            }
            disabled={busy || !selectedSubreddit}
          >
            Scrape Selected
          </Button>
        </div>
      </Card>

      <Card className="p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="text-lg font-semibold">Saved Subreddits</h2>
          <div className="relative w-full sm:w-72">
            <span className="absolute left-3 top-3 text-xs font-bold text-muted">S</span>
            <Input
              className="pl-9"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search saved names"
            />
          </div>
        </div>
        {loading ? (
          <div className="mt-4">
            <StateMessage title="Loading subreddits..." description="Fetching saved names and health." compact />
          </div>
        ) : (
          <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {filteredSubreddits.map((item) => (
              <div
                key={item.id}
                className={`flex items-center justify-between gap-2 rounded-md border p-3 ${
                  selectedSubreddit === item.name
                    ? "border-slate-900 bg-slate-50"
                    : "border-border bg-white"
                }`}
              >
                <button className="min-w-0 text-left" onClick={() => setSelectedSubreddit(item.name)}>
                  <div className="truncate font-medium">r/{item.name}</div>
                  <div className="text-xs text-muted">Added {formatDate(item.created_at)}</div>
                </button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    runAction(async () => {
                      await api.deleteSubreddit(item.id);
                      await load();
                    }, "Subreddit removed")
                  }
                  aria-label={`Delete ${item.name}`}
                >
                  Del
                </Button>
              </div>
            ))}
          </div>
        )}
        {!loading && !filteredSubreddits.length && (
          <EmptyState
            title="No saved subreddits"
            description="Add a subreddit name to start collecting posts, comments, and reply drafts."
          />
        )}
        <RecentRuns runs={scrapeRuns} />
      </Card>

      <SubredditHealthTable rows={healthRows} onSelect={setSelectedSubreddit} />
    </div>
  );
}

function SubredditHealthTable({
  rows,
  onSelect,
}: {
  rows: SubredditHealthItem[];
  onSelect: (name: string) => void;
}) {
  return (
    <Card className="overflow-hidden xl:col-span-2">
      <div className="border-b border-border p-4">
        <h2 className="text-lg font-semibold">Subreddit Health</h2>
        <p className="text-sm text-muted">
          Operational view of scrape freshness, content volume, reply load, and errors.
        </p>
      </div>
      <div className="overflow-x-auto">
        <TableShell minWidth={860}>
          <thead className={tableHeadClassName}>
            <tr>
              <th className={tableCellClassName}>Subreddit</th>
              <th className={tableCellClassName}>Posts</th>
              <th className={tableCellClassName}>Comments</th>
              <th className={tableCellClassName}>Pending</th>
              <th className={tableCellClassName}>Done</th>
              <th className={tableCellClassName}>Promo</th>
              <th className={tableCellClassName}>Last scrape</th>
              <th className={tableCellClassName}>Errors</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.subreddit} className={tableRowClassName}>
                <td className={tableCellClassName}>
                  <button className="font-medium text-accent" onClick={() => onSelect(row.subreddit)}>
                    r/{row.subreddit}
                  </button>
                </td>
                <td className={tableCellClassName}>{row.total_posts}</td>
                <td className={tableCellClassName}>{row.total_comments}</td>
                <td className={tableCellClassName}>{row.pending_replies}</td>
                <td className={tableCellClassName}>{row.done_replies}</td>
                <td className={tableCellClassName}>{row.promo_replies}</td>
                <td className={tableCellClassName}>
                  <div>{formatDate(row.latest_scrape_time)}</div>
                  {row.latest_scrape_status && (
                    <div className="text-xs text-muted">{row.latest_scrape_status}</div>
                  )}
                </td>
                <td className={`${tableCellClassName} ${row.error_count ? "text-danger" : ""}`}>
                  {row.error_count}
                </td>
              </tr>
            ))}
          </tbody>
        </TableShell>
      </div>
      {!rows.length && (
        <div className="p-4">
          <EmptyState
            title="No health data yet"
            description="Track and scrape a subreddit to populate the health table."
          />
        </div>
      )}
    </Card>
  );
}

function RecentRuns({ runs }: { runs: ScrapeRun[] }) {
  return (
    <div className="mt-5">
      <h3 className="mb-2 text-sm font-semibold uppercase text-muted">Recent scrape status</h3>
      <div className="space-y-2">
        {runs.slice(0, 4).map((run) => (
          <div key={run.id} className="rounded-md border border-border bg-slate-50 p-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium">r/{run.subreddit}</span>
              <Badge>{run.status}</Badge>
            </div>
            <div className="mt-1 text-xs text-muted">
              {run.posts_count} posts - {run.comments_count} comments - {formatDate(run.created_at)}
            </div>
            {run.error_message && (
              <div className="mt-2 text-xs text-danger">{run.error_message}</div>
            )}
          </div>
        ))}
        {!runs.length && (
          <EmptyState
            title="No scrape runs yet"
            description="Run a selected or full scrape to see job status here."
            compact
          />
        )}
      </div>
    </div>
  );
}
