"use client";

import { useEffect, useMemo, useState } from "react";
import { api, type ContentPost, type DashboardSearchResult, type DashboardSummary, type ReplyItem, type ScrapeRun, type ScrapeRunList, type SubredditContent, type SubredditHealthItem, type TrackedSubreddit } from "@/lib/api";
import { formatDate, percent } from "@/lib/utils";
import { Badge, Button, Card, Input, Select, Skeleton, Textarea, buttonClassName } from "@/components/ui";

type Section = "subreddits" | "feed" | "replies" | "analytics" | "logs";
type RelevanceFilter = "all" | "promo" | "normal";

const navItems: { id: Section; label: string; icon: string }[] = [
  { id: "subreddits", label: "Subreddits", icon: "SB" },
  { id: "feed", label: "Feed", icon: "FD" },
  { id: "replies", label: "Replies", icon: "RP" },
  { id: "analytics", label: "Analytics", icon: "AN" },
  { id: "logs", label: "Logs", icon: "LG" },
];

const replyStatuses = ["PENDING", "DONE", "DISMISSED", "APPROVED", "POSTING", "POSTED", "FAILED"];

function replyValue(reply: ReplyItem) {
  return Math.max(reply.post_upvotes, 0) * 3 + Math.max(reply.comment_upvotes, 0) * 4 + Math.max(reply.post_comment_count, 0);
}

export default function DashboardPage() {
  const [section, setSection] = useState<Section>("subreddits");
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [subreddits, setSubreddits] = useState<TrackedSubreddit[]>([]);
  const [selectedSubreddit, setSelectedSubreddit] = useState("");
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [content, setContent] = useState<SubredditContent | null>(null);
  const [scrapeRuns, setScrapeRuns] = useState<ScrapeRunList | null>(null);
  const [healthRows, setHealthRows] = useState<SubredditHealthItem[]>([]);
  const [searchResults, setSearchResults] = useState<DashboardSearchResult[]>([]);
  const [replies, setReplies] = useState<Record<string, ReplyItem[]>>({});
  const [feedPage, setFeedPage] = useState(1);
  const [logsPage, setLogsPage] = useState(1);
  const [scrapeLimit, setScrapeLimit] = useState(5);
  const [newSubreddit, setNewSubreddit] = useState("");
  const [query, setQuery] = useState("");
  const [globalSearch, setGlobalSearch] = useState("");
  const [searchAttempted, setSearchAttempted] = useState(false);
  const [relevance, setRelevance] = useState<RelevanceFilter>("all");
  const [minPostUpvotes, setMinPostUpvotes] = useState(0);
  const [minCommentUpvotes, setMinCommentUpvotes] = useState(0);
  const [replySort, setReplySort] = useState("value");
  const [replySearch, setReplySearch] = useState("");
  const [replyPageSize, setReplyPageSize] = useState(10);
  const [selectedReplyIds, setSelectedReplyIds] = useState<number[]>([]);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  async function refreshBase() {
    const [tracked, nextSummary, runs, nextHealthRows, replyGroups] = await Promise.all([
      api.trackedSubreddits(),
      api.summary(),
      api.scrapeRuns(logsPage, 8, selectedSubreddit || undefined),
      api.subredditHealth(),
      Promise.all(replyStatuses.map((status) => api.replies(status, 200, selectedSubreddit || undefined))),
    ]);
    setSubreddits(tracked);
    setSummary(nextSummary);
    setScrapeRuns(runs);
    setHealthRows(nextHealthRows);
    setReplies(Object.fromEntries(replyStatuses.map((status, index) => [status, replyGroups[index]])));
    if (!selectedSubreddit && tracked[0]) setSelectedSubreddit(tracked[0].name);
  }

  async function refreshContent(subreddit = selectedSubreddit) {
    if (!subreddit) {
      setContent(null);
      return;
    }
    setContent(await api.content(subreddit, feedPage, 5, 5, dateFrom, dateTo));
  }

  async function refreshAll() {
    setError("");
    try {
      setLoading(true);
      await refreshBase();
      await refreshContent();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard data");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refreshAll();
    const timer = window.setInterval(() => {
      refreshBase().catch((err) => setError(err instanceof Error ? err.message : "Refresh failed"));
    }, 15000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    refreshContent().catch((err) => setError(err instanceof Error ? err.message : "Feed refresh failed"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSubreddit, feedPage, dateFrom, dateTo]);

  useEffect(() => {
    refreshBase().catch((err) => setError(err instanceof Error ? err.message : "Refresh failed"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSubreddit, logsPage]);

  const filteredSubreddits = useMemo(
    () => subreddits.filter((item) => item.name.toLowerCase().includes(query.toLowerCase())),
    [subreddits, query],
  );

  const pendingReplies = useMemo(() => {
    let items = [...(replies.PENDING || [])];
    if (relevance === "promo") items = items.filter((item) => item.includes_promo);
    if (relevance === "normal") items = items.filter((item) => !item.includes_promo);
    items = items.filter(
      (item) => item.post_upvotes >= minPostUpvotes && item.comment_upvotes >= minCommentUpvotes,
    );
    items.sort((a, b) => {
      if (replySort === "comment") return b.comment_upvotes - a.comment_upvotes;
      if (replySort === "post") return b.post_upvotes - a.post_upvotes;
      if (replySort === "newest") return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      return replyValue(b) - replyValue(a);
    });
    return items;
  }, [minCommentUpvotes, minPostUpvotes, relevance, replies, replySort]);

  async function runSearch() {
    if (globalSearch.trim().length < 2) {
      setSearchResults([]);
      setSearchAttempted(false);
      return;
    }
    await runAction(async () => {
      setSearchResults(await api.search(globalSearch.trim()));
      setSearchAttempted(true);
    }, "Search complete");
  }

  async function logout() {
    await fetch("/api/login", { method: "DELETE" });
    window.location.assign("/login");
  }

  async function runAction(action: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(success);
      await refreshAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  const totalReplies = (summary?.promo_replies || 0) + (summary?.normal_replies || 0);
  const nav = (
    <aside className="flex h-full flex-col border-r border-border bg-white">
      <div className="border-b border-border px-5 py-5">
        <div className="text-lg font-semibold tracking-tight">Reddit Reply Ops</div>
        <div className="mt-1 text-sm text-muted">Scrape, draft, post, monitor.</div>
      </div>
      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map((item) => {
          return (
            <button
              key={item.id}
              onClick={() => {
                setSection(item.id);
                setMobileNavOpen(false);
              }}
              className={`flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium ${
                section === item.id ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100"
              }`}
            >
              <span className="flex h-6 w-6 items-center justify-center rounded bg-slate-100 text-[10px] font-bold text-slate-700">
                {item.icon}
              </span>
              {item.label}
            </button>
          );
        })}
      </nav>
      <div className="space-y-3 border-t border-border p-4">
        <div className="text-xs text-muted">Last scrape: {formatDate(summary?.latest_scrape_time)}</div>
        <Button variant="secondary" className="w-full" onClick={logout}>
          Logout
        </Button>
      </div>
    </aside>
  );

  return (
    <main className="min-h-screen bg-background">
      <div className="grid min-h-screen lg:grid-cols-[260px_1fr]">
        <div className="hidden lg:block">{nav}</div>
        {mobileNavOpen && <div className="fixed inset-0 z-40 bg-black/30 lg:hidden" onClick={() => setMobileNavOpen(false)} />}
        <div className={`fixed inset-y-0 left-0 z-50 w-72 transform lg:hidden ${mobileNavOpen ? "translate-x-0" : "-translate-x-full"} transition-transform`}>
          {nav}
        </div>

        <div className="min-w-0">
          <header className="sticky top-0 z-30 border-b border-border bg-background/95 px-4 py-3 backdrop-blur md:px-6">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <Button variant="secondary" size="sm" className="lg:hidden" onClick={() => setMobileNavOpen(true)} aria-label="Open navigation">
                  Menu
                </Button>
                <div>
                  <h1 className="text-xl font-semibold tracking-tight md:text-2xl">Dashboard</h1>
                  <p className="text-sm text-muted">Selected scope: {selectedSubreddit ? `r/${selectedSubreddit}` : "All subreddits"}</p>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Button variant="secondary" onClick={refreshAll} disabled={loading || busy}>
                  <span className={loading ? "animate-spin" : ""}>R</span>
                  Refresh
                </Button>
                <Button variant="secondary" onClick={logout}>
                  Logout
                </Button>
              </div>
            </div>
          </header>

          <div className="space-y-5 p-4 md:p-6">
            {error && <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-danger">{error}</div>}
            {notice && <div className="rounded-md border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-accent">{notice}</div>}

            {loading && !summary ? (
              <div className="grid gap-4 md:grid-cols-4">
                {Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-28" />)}
              </div>
            ) : (
              <StatsGrid summary={summary} totalReplies={totalReplies} />
            )}

            <GlobalSearch
              value={globalSearch}
              results={searchResults}
              busy={busy}
              attempted={searchAttempted}
              onChange={setGlobalSearch}
              onSearch={runSearch}
              onClear={() => {
                setGlobalSearch("");
                setSearchResults([]);
                setSearchAttempted(false);
              }}
            />

            {section === "subreddits" && (
              <SubredditSection
                subreddits={filteredSubreddits}
                selected={selectedSubreddit}
                query={query}
                newSubreddit={newSubreddit}
                scrapeLimit={scrapeLimit}
                busy={busy}
                onQuery={setQuery}
                onNewSubreddit={setNewSubreddit}
                onScrapeLimit={setScrapeLimit}
                onSelect={(name) => {
                  setSelectedSubreddit(name);
                  setFeedPage(1);
                }}
                onAdd={() => runAction(async () => {
                  if (!newSubreddit.trim()) return;
                  await api.addSubreddit(newSubreddit.trim());
                  setNewSubreddit("");
                }, "Subreddit saved")}
                onDelete={(id) => runAction(() => api.deleteSubreddit(id), "Subreddit removed")}
                onScrapeSelected={() => selectedSubreddit && runAction(() => api.scrapeSelected(selectedSubreddit, scrapeLimit), `Queued r/${selectedSubreddit}`)}
                onScrapeAll={() => runAction(() => api.scrapeAll(scrapeLimit), "Queued all tracked subreddits")}
                runs={scrapeRuns?.runs || []}
                healthRows={healthRows}
              />
            )}

            {section === "feed" && (
              <FeedSection
                content={content}
                selected={selectedSubreddit}
                subreddits={subreddits}
                page={feedPage}
                relevance={relevance}
                dateFrom={dateFrom}
                dateTo={dateTo}
                onSelect={(name) => {
                  setSelectedSubreddit(name);
                  setFeedPage(1);
                }}
                onRelevance={setRelevance}
                onDateFrom={setDateFrom}
                onDateTo={setDateTo}
                onPage={setFeedPage}
              />
            )}

            {section === "replies" && (
              <RepliesSection
                pending={pendingReplies}
                done={replies.DONE || []}
                dismissed={replies.DISMISSED || []}
                approved={replies.APPROVED || []}
                posting={replies.POSTING || []}
                posted={replies.POSTED || []}
                failed={replies.FAILED || []}
                busy={busy}
                minPostUpvotes={minPostUpvotes}
                minCommentUpvotes={minCommentUpvotes}
                replySort={replySort}
                selectedReplyIds={selectedReplyIds}
                onMinPostUpvotes={setMinPostUpvotes}
                onMinCommentUpvotes={setMinCommentUpvotes}
                onReplySort={setReplySort}
                replySearch={replySearch}
                replyPageSize={replyPageSize}
                onReplySearch={setReplySearch}
                onReplyPageSize={setReplyPageSize}
                onSelectedReplyIds={setSelectedReplyIds}
                onApprove={(reply) => runAction(() => api.updateReply(reply.reply_id, { status: "APPROVED", reply_text: reply.reply_text }), "Draft approved for posting")}
                onDone={(reply, text) => runAction(() => api.updateReply(reply.reply_id, { status: "DONE", reply_text: text }), "Reply marked done")}
                onSave={(reply, text) => runAction(() => api.updateReply(reply.reply_id, { reply_text: text }), "Draft saved")}
                onDismiss={(reply) => {
                  if (window.confirm(`Dismiss reply #${reply.reply_id}?`)) {
                    runAction(() => api.updateReply(reply.reply_id, { status: "DISMISSED" }), "Reply dismissed");
                  }
                }}
                onRetry={(reply) => runAction(() => api.updateReply(reply.reply_id, { status: "APPROVED" }), "Failed reply re-approved")}
                onBulk={(status) => {
                  if (window.confirm(`Update ${selectedReplyIds.length} selected replies to ${status}?`)) {
                    runAction(async () => {
                      await api.bulkUpdateReplies(selectedReplyIds, status);
                      setSelectedReplyIds([]);
                    }, `Bulk updated ${selectedReplyIds.length} replies`);
                  }
                }}
              />
            )}

            {section === "analytics" && <AnalyticsSection summary={summary} />}

            {section === "logs" && (
              <LogsSection
                runs={scrapeRuns}
                page={logsPage}
                workerCounts={summary?.worker_counts || {}}
                onPage={setLogsPage}
              />
            )}
          </div>
        </div>
      </div>
    </main>
  );
}

function StatsGrid({ summary, totalReplies }: { summary: DashboardSummary | null; totalReplies: number }) {
  const cards: { label: string; value: string | number; icon: string }[] = [
    { label: "Subreddits", value: summary?.total_subreddits || 0, icon: "SB" },
    { label: "Posts fetched", value: summary?.total_posts || 0, icon: "PO" },
    { label: "Comments fetched", value: summary?.total_comments || 0, icon: "CO" },
    { label: "Pending replies", value: summary?.reply_counts?.PENDING || 0, icon: "PE" },
    { label: "Done replies", value: summary?.reply_counts?.DONE || 0, icon: "DO" },
    { label: "Promo ratio", value: percent(summary?.promo_ratio || 0), icon: "PR" },
    { label: "Worker active", value: summary?.worker_counts?.POSTING || 0, icon: "WK" },
    { label: "Total replies", value: totalReplies, icon: "TR" },
  ];
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map(({ label, value, icon }) => (
        <Card key={label} className="p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-xs font-semibold uppercase text-muted">{label}</div>
              <div className="mt-2 text-2xl font-semibold">{value}</div>
            </div>
            <div className="rounded-md bg-slate-100 p-2">
              <span className="flex h-6 w-6 items-center justify-center text-xs font-bold text-slate-700">{icon}</span>
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}

function GlobalSearch(props: {
  value: string;
  results: DashboardSearchResult[];
  busy: boolean;
  attempted: boolean;
  onChange: (value: string) => void;
  onSearch: () => void;
  onClear: () => void;
}) {
  return (
    <Card className="p-4">
      <div className="grid gap-3 lg:grid-cols-[1fr_auto_auto]">
        <Input
          value={props.value}
          onChange={(event) => props.onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") props.onSearch();
          }}
          placeholder="Search posts, comments, and reply drafts"
        />
        <Button onClick={props.onSearch} disabled={props.busy || props.value.trim().length < 2}>Search</Button>
        <Button variant="secondary" onClick={props.onClear}>Clear</Button>
      </div>
      {!!props.results.length && (
        <div className="mt-4 grid gap-2 lg:grid-cols-2">
          {props.results.map((result) => (
            <div key={`${result.kind}-${result.id}`} className="rounded-md border border-border bg-slate-50 p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <Badge>{result.kind}</Badge>
                {result.status && <Badge>{result.status}</Badge>}
                {result.includes_promo && <Badge className="border-amber-200 bg-amber-50 text-warning">promo</Badge>}
                <span className="text-muted">r/{result.subreddit}</span>
              </div>
              <div className="mt-2 font-medium">{result.title}</div>
              <p className="mt-1 line-clamp-2 text-slate-700">{result.text}</p>
              <div className="mt-2 flex items-center justify-between gap-2 text-xs text-muted">
                <span>{formatDate(result.created_at)}</span>
                {result.url && <a className="font-medium text-accent" href={result.url} target="_blank" rel="noreferrer">Open</a>}
              </div>
            </div>
          ))}
        </div>
      )}
      {props.attempted && !props.busy && !props.results.length && (
        <EmptyState title="No search matches" description="Try a subreddit name, post title, comment text, or reply draft phrase." />
      )}
    </Card>
  );
}

function SubredditSection(props: {
  subreddits: TrackedSubreddit[];
  selected: string;
  query: string;
  newSubreddit: string;
  scrapeLimit: number;
  busy: boolean;
  runs: ScrapeRun[];
  healthRows: SubredditHealthItem[];
  onQuery: (value: string) => void;
  onNewSubreddit: (value: string) => void;
  onScrapeLimit: (value: number) => void;
  onSelect: (name: string) => void;
  onAdd: () => void;
  onDelete: (id: number) => void;
  onScrapeSelected: () => void;
  onScrapeAll: () => void;
}) {
  return (
    <div className="grid gap-5 xl:grid-cols-[380px_1fr]">
      <Card className="p-4">
        <h2 className="text-lg font-semibold">Subreddit Management</h2>
        <div className="mt-4 grid gap-3">
          <div className="flex gap-2">
            <Input value={props.newSubreddit} onChange={(event) => props.onNewSubreddit(event.target.value)} placeholder="Add subreddit, e.g. SaaS" />
            <Button onClick={props.onAdd} disabled={props.busy || !props.newSubreddit.trim()} aria-label="Add subreddit">
              Add
            </Button>
          </div>
          <div className="grid grid-cols-[1fr_110px] gap-2">
            <Input type="number" min={1} max={500} value={props.scrapeLimit} onChange={(event) => props.onScrapeLimit(Number(event.target.value))} />
            <Button variant="accent" onClick={props.onScrapeAll} disabled={props.busy}>Scrape All</Button>
          </div>
          <Button variant="secondary" onClick={props.onScrapeSelected} disabled={props.busy || !props.selected}>
            Scrape Selected
          </Button>
        </div>
      </Card>

      <Card className="p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="text-lg font-semibold">Saved Subreddits</h2>
          <div className="relative w-full sm:w-72">
            <span className="absolute left-3 top-3 text-xs font-bold text-muted">S</span>
            <Input className="pl-9" value={props.query} onChange={(event) => props.onQuery(event.target.value)} placeholder="Search saved names" />
          </div>
        </div>
        <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {props.subreddits.map((item) => (
            <div key={item.id} className={`flex items-center justify-between gap-2 rounded-md border p-3 ${props.selected === item.name ? "border-slate-900 bg-slate-50" : "border-border bg-white"}`}>
              <button className="min-w-0 text-left" onClick={() => props.onSelect(item.name)}>
                <div className="truncate font-medium">r/{item.name}</div>
                <div className="text-xs text-muted">Added {formatDate(item.created_at)}</div>
              </button>
              <Button variant="ghost" size="sm" onClick={() => props.onDelete(item.id)} aria-label={`Delete ${item.name}`}>
                Del
              </Button>
            </div>
          ))}
        </div>
        {!props.subreddits.length && (
          <EmptyState title="No saved subreddits" description="Add a subreddit name to start collecting posts, comments, and reply drafts." />
        )}
        <RecentRuns runs={props.runs} />
      </Card>
      <SubredditHealthTable rows={props.healthRows} onSelect={props.onSelect} />
    </div>
  );
}

function SubredditHealthTable({ rows, onSelect }: { rows: SubredditHealthItem[]; onSelect: (name: string) => void }) {
  return (
    <Card className="overflow-hidden xl:col-span-2">
      <div className="border-b border-border p-4">
        <h2 className="text-lg font-semibold">Subreddit Health</h2>
        <p className="text-sm text-muted">Operational view of scrape freshness, content volume, reply load, and errors.</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-muted">
            <tr>
              <th className="px-4 py-3">Subreddit</th>
              <th className="px-4 py-3">Posts</th>
              <th className="px-4 py-3">Comments</th>
              <th className="px-4 py-3">Pending</th>
              <th className="px-4 py-3">Done</th>
              <th className="px-4 py-3">Promo</th>
              <th className="px-4 py-3">Last scrape</th>
              <th className="px-4 py-3">Errors</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.subreddit} className="border-t border-border">
                <td className="px-4 py-3">
                  <button className="font-medium text-accent" onClick={() => onSelect(row.subreddit)}>r/{row.subreddit}</button>
                </td>
                <td className="px-4 py-3">{row.total_posts}</td>
                <td className="px-4 py-3">{row.total_comments}</td>
                <td className="px-4 py-3">{row.pending_replies}</td>
                <td className="px-4 py-3">{row.done_replies}</td>
                <td className="px-4 py-3">{row.promo_replies}</td>
                <td className="px-4 py-3">
                  <div>{formatDate(row.latest_scrape_time)}</div>
                  {row.latest_scrape_status && <div className="text-xs text-muted">{row.latest_scrape_status}</div>}
                </td>
                <td className={`px-4 py-3 ${row.error_count ? "text-danger" : ""}`}>{row.error_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!rows.length && (
        <div className="p-4">
          <EmptyState title="No health data yet" description="Track and scrape a subreddit to populate the health table." />
        </div>
      )}
    </Card>
  );
}

function FeedSection(props: {
  content: SubredditContent | null;
  selected: string;
  subreddits: TrackedSubreddit[];
  page: number;
  relevance: RelevanceFilter;
  dateFrom: string;
  dateTo: string;
  onSelect: (name: string) => void;
  onRelevance: (value: RelevanceFilter) => void;
  onDateFrom: (value: string) => void;
  onDateTo: (value: string) => void;
  onPage: (value: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil((props.content?.total_posts || 0) / (props.content?.page_size || 5)));
  return (
    <Card className="p-4">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <h2 className="text-lg font-semibold">Subreddit Feed</h2>
          <p className="text-sm text-muted">Posts, comments, pagination, and filters for the selected subreddit.</p>
        </div>
        <div className="grid gap-2 sm:grid-cols-4 xl:w-[760px]">
          <Select value={props.selected} onChange={(event) => props.onSelect(event.target.value)}>
            {props.subreddits.map((item) => <option key={item.id} value={item.name}>r/{item.name}</option>)}
          </Select>
          <Select value={props.relevance} onChange={(event) => props.onRelevance(event.target.value as RelevanceFilter)}>
            <option value="all">All relevance</option>
            <option value="promo">sentx.ai promo</option>
            <option value="normal">Normal</option>
          </Select>
          <Input type="date" value={props.dateFrom} onChange={(event) => props.onDateFrom(event.target.value)} />
          <Input type="date" value={props.dateTo} onChange={(event) => props.onDateTo(event.target.value)} />
        </div>
      </div>
      <div className="mt-4 space-y-3">
        {(props.content?.posts || []).map((post) => <PostCard key={post.id} post={post} />)}
        {!props.subreddits.length && (
          <EmptyState title="No subreddits tracked" description="Add a subreddit before viewing the feed." />
        )}
        {!!props.subreddits.length && !props.content?.posts?.length && (
          <EmptyState title="No posts found" description="Change the date filters or run a fresh scrape for this subreddit." />
        )}
      </div>
      <Pagination page={props.page} totalPages={totalPages} total={props.content?.total_posts || 0} onPage={props.onPage} />
    </Card>
  );
}

function PostCard({ post }: { post: ContentPost }) {
  return (
    <div className="rounded-lg border border-border bg-white p-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-base font-semibold">{post.title}</h3>
          <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted">
            <span>{post.upvotes} upvotes</span>
            <span>{post.number_of_comments} comments</span>
            <span>{formatDate(post.created_at)}</span>
          </div>
        </div>
        <a className="inline-flex items-center gap-1 text-sm font-medium text-accent" href={post.url} target="_blank" rel="noreferrer">
          Open
        </a>
      </div>
      {post.body && <p className="mt-3 line-clamp-4 text-sm leading-6 text-slate-700">{post.body}</p>}
      <div className="mt-4 space-y-2">
        {post.top_comments.map((comment) => (
          <div key={comment.id} className="rounded-md border-l-4 border-teal-600 bg-slate-50 p-3 text-sm">
            <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted">
              <span>{comment.upvotes} upvotes</span>
              <span>{comment.author || "unknown"}</span>
              <span>{formatDate(comment.created_at)}</span>
              {comment.comment_url && <a className="text-accent" href={comment.comment_url} target="_blank" rel="noreferrer">Open comment</a>}
            </div>
            {comment.text}
          </div>
        ))}
      </div>
    </div>
  );
}

function RepliesSection(props: {
  pending: ReplyItem[];
  done: ReplyItem[];
  dismissed: ReplyItem[];
  approved: ReplyItem[];
  posting: ReplyItem[];
  posted: ReplyItem[];
  failed: ReplyItem[];
  busy: boolean;
  minPostUpvotes: number;
  minCommentUpvotes: number;
  replySort: string;
  replySearch: string;
  replyPageSize: number;
  selectedReplyIds: number[];
  onMinPostUpvotes: (value: number) => void;
  onMinCommentUpvotes: (value: number) => void;
  onReplySort: (value: string) => void;
  onReplySearch: (value: string) => void;
  onReplyPageSize: (value: number) => void;
  onSelectedReplyIds: (value: number[]) => void;
  onApprove: (reply: ReplyItem) => void;
  onDone: (reply: ReplyItem, text: string) => void;
  onSave: (reply: ReplyItem, text: string) => void;
  onDismiss: (reply: ReplyItem) => void;
  onRetry: (reply: ReplyItem) => void;
  onBulk: (status: string) => void;
}) {
  const search = props.replySearch.trim().toLowerCase();
  const matchesSearch = (reply: ReplyItem) => {
    if (!search) return true;
    return [
      reply.reply_text,
      reply.comment_text,
      reply.post_title,
      reply.subreddit,
      String(reply.reply_id),
    ].some((value) => value.toLowerCase().includes(search));
  };
  const pending = props.pending.filter(matchesSearch);
  const done = props.done.filter(matchesSearch);
  const dismissed = props.dismissed.filter(matchesSearch);
  const approved = props.approved.filter(matchesSearch);
  const posting = props.posting.filter(matchesSearch);
  const posted = props.posted.filter(matchesSearch);
  const failed = props.failed.filter(matchesSearch);
  const pendingIds = pending.map((item) => item.reply_id);
  return (
    <div className="space-y-5">
      <Card className="p-4">
        <div className="grid gap-3 lg:grid-cols-6">
          <div className="lg:col-span-2">
            <label className="mb-1 block text-xs font-semibold uppercase text-muted">Search replies</label>
            <Input
              value={props.replySearch}
              onChange={(event) => props.onReplySearch(event.target.value)}
              placeholder="Search draft, comment, title, subreddit, or ID"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase text-muted">Sort</label>
            <Select value={props.replySort} onChange={(event) => props.onReplySort(event.target.value)}>
              <option value="value">Best value</option>
              <option value="comment">Comment upvotes</option>
              <option value="post">Post upvotes</option>
              <option value="newest">Newest</option>
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase text-muted">Min post upvotes</label>
            <Input type="number" min={0} value={props.minPostUpvotes} onChange={(event) => props.onMinPostUpvotes(Number(event.target.value))} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase text-muted">Min comment upvotes</label>
            <Input type="number" min={0} value={props.minCommentUpvotes} onChange={(event) => props.onMinCommentUpvotes(Number(event.target.value))} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase text-muted">Page size</label>
            <Select value={String(props.replyPageSize)} onChange={(event) => props.onReplyPageSize(Number(event.target.value))}>
              <option value="5">5 replies</option>
              <option value="10">10 replies</option>
              <option value="25">25 replies</option>
              <option value="50">50 replies</option>
            </Select>
          </div>
          <Button
            className="self-end"
            variant="secondary"
            onClick={() => props.onSelectedReplyIds(props.selectedReplyIds.length === pendingIds.length ? [] : pendingIds)}
            disabled={!pendingIds.length}
          >
            {props.selectedReplyIds.length === pendingIds.length ? "Clear selection" : "Select filtered"}
          </Button>
          <div className="grid grid-cols-3 gap-2 self-end lg:col-span-2">
            <Button disabled={props.busy || !props.selectedReplyIds.length} onClick={() => props.onBulk("APPROVED")}>Bulk approve</Button>
            <Button disabled={props.busy || !props.selectedReplyIds.length} variant="secondary" onClick={() => props.onBulk("DONE")}>Bulk done</Button>
            <Button disabled={props.busy || !props.selectedReplyIds.length} variant="secondary" onClick={() => props.onBulk("DISMISSED")}>Dismiss</Button>
          </div>
        </div>
        <div className="mt-3 text-sm text-muted">{props.selectedReplyIds.length} selected from {pending.length} matching pending replies.</div>
      </Card>
      <ReplyGroup
        title="Pending promotional replies"
        replies={pending.filter((item) => item.includes_promo)}
        busy={props.busy}
        pageSize={props.replyPageSize}
        selectedReplyIds={props.selectedReplyIds}
        onSelectedReplyIds={props.onSelectedReplyIds}
        onApprove={props.onApprove}
        onDone={props.onDone}
        onSave={props.onSave}
        onDismiss={props.onDismiss}
      />
      <ReplyGroup
        title="Pending normal replies"
        replies={pending.filter((item) => !item.includes_promo)}
        busy={props.busy}
        pageSize={props.replyPageSize}
        selectedReplyIds={props.selectedReplyIds}
        onSelectedReplyIds={props.onSelectedReplyIds}
        onApprove={props.onApprove}
        onDone={props.onDone}
        onSave={props.onSave}
        onDismiss={props.onDismiss}
      />
      <QueueGroup title="Posting queue" groups={[["Approved", approved], ["Posting", posting], ["Failed", failed], ["Posted", posted]]} busy={props.busy} pageSize={props.replyPageSize} onRetry={props.onRetry} />
      <ReplyGroup title="Dismissed replies" replies={dismissed} busy={props.busy} pageSize={props.replyPageSize} doneOnly selectedReplyIds={[]} onSelectedReplyIds={() => {}} onApprove={props.onApprove} onDone={props.onDone} onSave={props.onSave} onDismiss={props.onDismiss} />
      <ReplyGroup title="Done replies" replies={done} busy={props.busy} pageSize={props.replyPageSize} doneOnly selectedReplyIds={[]} onSelectedReplyIds={() => {}} onApprove={props.onApprove} onDone={props.onDone} onSave={props.onSave} onDismiss={props.onDismiss} />
    </div>
  );
}

function ReplyGroup({ title, replies, busy, pageSize, doneOnly, selectedReplyIds, onSelectedReplyIds, onApprove, onDone, onSave, onDismiss }: { title: string; replies: ReplyItem[]; busy: boolean; pageSize: number; doneOnly?: boolean; selectedReplyIds: number[]; onSelectedReplyIds: (value: number[]) => void; onApprove: (reply: ReplyItem) => void; onDone: (reply: ReplyItem, text: string) => void; onSave: (reply: ReplyItem, text: string) => void; onDismiss: (reply: ReplyItem) => void }) {
  const [page, setPage] = useState(1);
  const totalPages = Math.max(1, Math.ceil(replies.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const visibleReplies = replies.slice((safePage - 1) * pageSize, safePage * pageSize);
  useEffect(() => {
    setPage(1);
  }, [pageSize, replies.length]);
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold">{title}</h2>
        <Badge>{replies.length}</Badge>
      </div>
      <div className="grid gap-3 xl:grid-cols-2">
        {visibleReplies.map((reply) => (
          <ReplyCard
            key={reply.reply_id}
            reply={reply}
            busy={busy}
            doneOnly={doneOnly}
            selected={selectedReplyIds.includes(reply.reply_id)}
            onSelected={(selected) => {
              if (selected) onSelectedReplyIds([...selectedReplyIds, reply.reply_id]);
              else onSelectedReplyIds(selectedReplyIds.filter((id) => id !== reply.reply_id));
            }}
            onApprove={onApprove}
            onDone={onDone}
            onSave={onSave}
            onDismiss={onDismiss}
          />
        ))}
      </div>
      {!replies.length && <EmptyState title="No replies in this view" description="Adjust the filters or search query to show more replies." />}
      {replies.length > pageSize && (
        <Pagination page={safePage} totalPages={totalPages} total={replies.length} onPage={setPage} />
      )}
    </Card>
  );
}

function ReplyCard({ reply, busy, doneOnly, selected, onSelected, onApprove, onDone, onSave, onDismiss }: { reply: ReplyItem; busy: boolean; doneOnly?: boolean; selected: boolean; onSelected: (selected: boolean) => void; onApprove: (reply: ReplyItem) => void; onDone: (reply: ReplyItem, text: string) => void; onSave: (reply: ReplyItem, text: string) => void; onDismiss: (reply: ReplyItem) => void }) {
  const [text, setText] = useState(reply.reply_text);
  const changed = text !== reply.reply_text;
  return (
    <div className="rounded-lg border border-border bg-white p-4">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        {!doneOnly && (
          <label className="flex items-center gap-2 text-slate-700">
            <input type="checkbox" checked={selected} onChange={(event) => onSelected(event.target.checked)} />
            Select
          </label>
        )}
        <Badge className={reply.includes_promo ? "border-amber-200 bg-amber-50 text-warning" : "border-teal-200 bg-teal-50 text-accent"}>
          {reply.includes_promo ? "sentx.ai promo" : "normal"}
        </Badge>
        <span>r/{reply.subreddit}</span>
        <span>{reply.comment_upvotes} comment upvotes</span>
        <span>{reply.post_upvotes} post upvotes</span>
        <span>value {replyValue(reply)}</span>
        <span>{reply.status}</span>
      </div>
      <h3 className="mt-3 font-semibold">{reply.post_title}</h3>
      <p className="mt-2 line-clamp-3 text-sm text-slate-700">{reply.comment_text}</p>
      <Textarea className="mt-3" value={text} onChange={(event) => setText(event.target.value)} readOnly={doneOnly} />
      <div className="mt-3 flex flex-wrap gap-2">
        {reply.comment_url && (
          <a className={buttonClassName("secondary", "sm")} href={reply.comment_url} target="_blank" rel="noreferrer">Comment</a>
        )}
        {!doneOnly && <Button variant="secondary" size="sm" onClick={() => onSave(reply, text)} disabled={busy || !text.trim() || !changed}>Save Draft</Button>}
        {!doneOnly && <Button variant="secondary" size="sm" onClick={() => onApprove({ ...reply, reply_text: text })} disabled={busy || !text.trim()}>Approve</Button>}
        {!doneOnly && <Button variant="secondary" size="sm" onClick={() => onDismiss(reply)} disabled={busy}>Dismiss</Button>}
        {!doneOnly && <Button size="sm" onClick={() => onDone(reply, text)} disabled={busy || !text.trim()}>Mark Done</Button>}
        {changed && <span className="self-center text-xs font-medium text-warning">Unsaved changes</span>}
      </div>
    </div>
  );
}

function QueueGroup({ title, groups, busy, pageSize, onRetry }: { title: string; groups: [string, ReplyItem[]][]; busy: boolean; pageSize: number; onRetry: (reply: ReplyItem) => void }) {
  return (
    <Card className="p-4">
      <h2 className="text-lg font-semibold">{title}</h2>
      <div className="mt-3 grid gap-3 xl:grid-cols-2">
        {groups.map(([label, items]) => (
          <QueueBucket key={label} label={label} items={items} busy={busy} pageSize={pageSize} onRetry={onRetry} />
        ))}
      </div>
    </Card>
  );
}

function QueueBucket({ label, items, busy, pageSize, onRetry }: { label: string; items: ReplyItem[]; busy: boolean; pageSize: number; onRetry: (reply: ReplyItem) => void }) {
  const [page, setPage] = useState(1);
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const visibleItems = items.slice((safePage - 1) * pageSize, safePage * pageSize);
  useEffect(() => {
    setPage(1);
  }, [items.length, pageSize]);

  return (
    <div className="rounded-lg border border-border bg-white p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="font-medium">{label}</div>
        <Badge>{items.length}</Badge>
      </div>
      <div className="space-y-2">
        {visibleItems.map((item) => (
          <div key={item.reply_id} className="rounded-md bg-slate-50 p-3 text-sm">
            <div className="font-medium">#{item.reply_id} r/{item.subreddit}</div>
            <p className="mt-1 line-clamp-2 text-muted">{item.reply_text}</p>
            {item.posting_error && <div className="mt-2 rounded bg-red-50 p-2 text-xs text-danger">{item.posting_error}</div>}
            {label === "Failed" && <Button className="mt-2" size="sm" variant="secondary" onClick={() => onRetry(item)} disabled={busy}>Retry</Button>}
          </div>
        ))}
        {!items.length && <EmptyState title="Empty queue" description={`No ${label.toLowerCase()} replies right now.`} compact />}
      </div>
      {items.length > pageSize && (
        <Pagination page={safePage} totalPages={totalPages} total={items.length} onPage={setPage} />
      )}
    </div>
  );
}

function AnalyticsSection({ summary }: { summary: DashboardSummary | null }) {
  const promo = summary?.promo_replies || 0;
  const normal = summary?.normal_replies || 0;
  const total = promo + normal;
  return (
    <div className="grid gap-5 xl:grid-cols-[1fr_420px]">
      <Card className="p-4">
        <h2 className="text-lg font-semibold">Analytics</h2>
        {summary ? (
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <RatioBar label="sentx.ai promotional replies" value={promo} total={total} className="bg-amber-500" />
            <RatioBar label="Normal replies" value={normal} total={total} className="bg-teal-600" />
            <RatioBar label="Pending replies" value={summary.reply_counts?.PENDING || 0} total={Math.max(1, total)} className="bg-slate-800" />
            <RatioBar label="Done replies" value={summary.reply_counts?.DONE || 0} total={Math.max(1, total)} className="bg-green-600" />
          </div>
        ) : (
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
          </div>
        )}
      </Card>
      <Card className="p-4">
        <h2 className="text-lg font-semibold">Latest Errors</h2>
        <div className="mt-3 space-y-2">
          {(summary?.latest_scrape_errors || []).map((run) => (
            <div key={run.id} className="rounded-md border border-red-100 bg-red-50 p-3 text-sm">
              <div className="font-medium">r/{run.subreddit} - {formatDate(run.created_at)}</div>
              <div className="mt-1 text-danger">{run.error_message}</div>
            </div>
          ))}
          {!summary?.latest_scrape_errors?.length && <EmptyState title="No scrape errors" description="Recent scrape runs have not recorded errors." compact />}
        </div>
      </Card>
    </div>
  );
}

function RatioBar({ label, value, total, className }: { label: string; value: number; total: number; className: string }) {
  const width = total ? Math.round((value / total) * 100) : 0;
  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-sm">
        <span className="font-medium">{label}</span>
        <span className="text-muted">{value}</span>
      </div>
      <div className="h-3 rounded-full bg-slate-100">
        <div className={`h-3 rounded-full ${className}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function LogsSection({ runs, page, workerCounts, onPage }: { runs: ScrapeRunList | null; page: number; workerCounts: Record<string, number>; onPage: (value: number) => void }) {
  const totalPages = Math.max(1, Math.ceil((runs?.total_runs || 0) / (runs?.page_size || 8)));
  return (
    <div className="space-y-5">
      <Card className="p-4">
        <h2 className="text-lg font-semibold">Worker Status</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-4">
          {["APPROVED", "POSTING", "POSTED", "FAILED"].map((status) => (
            <div key={status} className="rounded-md border border-border bg-white p-3">
              <div className="text-xs font-semibold text-muted">{status}</div>
              <div className="mt-1 text-2xl font-semibold">{workerCounts[status] || 0}</div>
            </div>
          ))}
        </div>
      </Card>
      <Card className="overflow-hidden">
        <div className="border-b border-border p-4">
          <h2 className="text-lg font-semibold">Live Scrape Logs</h2>
          <p className="text-sm text-muted">Polling recent scrape run records, status, counts, and errors.</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-muted">
              <tr>
                <th className="px-4 py-3">Subreddit</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Source</th>
                <th className="px-4 py-3">Counts</th>
                <th className="px-4 py-3">Started</th>
                <th className="px-4 py-3">Finished</th>
                <th className="px-4 py-3">Error</th>
              </tr>
            </thead>
            <tbody>
              {(runs?.runs || []).map((run) => (
                <tr key={run.id} className="border-t border-border">
                  <td className="px-4 py-3 font-medium">r/{run.subreddit}</td>
                  <td className="px-4 py-3"><Badge>{run.status}</Badge></td>
                  <td className="px-4 py-3">{run.source}</td>
                  <td className="px-4 py-3">{run.posts_count} posts - {run.comments_count} comments - {run.replies_count} replies</td>
                  <td className="px-4 py-3">{formatDate(run.created_at)}</td>
                  <td className="px-4 py-3">{formatDate(run.finished_at)}</td>
                  <td className="px-4 py-3 text-danger">{run.error_message || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!runs?.runs?.length && (
          <div className="p-4">
            <EmptyState title="No scrape logs" description="Scrape runs will appear here after jobs are queued or completed." />
          </div>
        )}
        <Pagination page={page} totalPages={totalPages} total={runs?.total_runs || 0} onPage={onPage} />
      </Card>
    </div>
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
            <div className="mt-1 text-xs text-muted">{run.posts_count} posts - {run.comments_count} comments - {formatDate(run.created_at)}</div>
            {run.error_message && <div className="mt-2 text-xs text-danger">{run.error_message}</div>}
          </div>
        ))}
        {!runs.length && <EmptyState title="No scrape runs yet" description="Run a selected or full scrape to see job status here." compact />}
      </div>
    </div>
  );
}

function EmptyState({ title, description, compact }: { title: string; description: string; compact?: boolean }) {
  return (
    <div className={`rounded-md border border-dashed border-border bg-slate-50 text-center ${compact ? "p-4" : "p-8"}`}>
      <div className="text-sm font-medium text-slate-800">{title}</div>
      <div className="mt-1 text-sm text-muted">{description}</div>
    </div>
  );
}

function Pagination({ page, totalPages, total, onPage }: { page: number; totalPages: number; total: number; onPage: (value: number) => void }) {
  return (
    <div className="mt-4 flex flex-col gap-2 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="text-sm text-muted">Page {page} of {totalPages} - {total} total</div>
      <div className="flex gap-2">
        <Button variant="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button>
        <Button variant="secondary" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>Next</Button>
      </div>
    </div>
  );
}
