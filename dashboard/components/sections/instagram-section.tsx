"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Card, Skeleton } from "@/components/legacy-ui";
import { useVisibleInterval } from "@/lib/hooks/use-visible-interval";
import { useNotice } from "@/lib/notice-context";
import {
  igApi,
  type IgAccount,
  type IgActionLog,
  type IgApproval,
  type IgComment,
  type IgCuratorPack,
  type IgCuratorRun,
  type IgPublicActionStat,
  type IgQueueCounts,
  type IgThread,
} from "@/lib/instagram";

type Tab = "overview" | "approvals" | "threads" | "comments" | "curator" | "accounts";

const TABS: { key: Tab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "approvals", label: "Approvals" },
  { key: "threads", label: "DMs" },
  { key: "comments", label: "Comments" },
  { key: "curator", label: "Curator" },
  { key: "accounts", label: "Accounts" },
];

const IG_UI_URL = process.env.NEXT_PUBLIC_INSTAGRAM_UI_URL || "http://localhost:8600";

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const seconds = Math.max(1, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function riskTone(level?: string): string {
  switch ((level || "").toLowerCase()) {
    case "high":
      return "bg-rose-500/15 text-rose-400 ring-1 ring-rose-500/20";
    case "medium":
      return "bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/20";
    default:
      return "bg-muted text-muted-foreground ring-1 ring-border";
  }
}

function participantLabel(t: IgThread): string {
  const p = t.participant_usernames;
  if (Array.isArray(p)) return p.join(", ") || t.instagram_thread_id;
  if (p && typeof p === "object") return Object.values(p).join(", ") || t.instagram_thread_id;
  return t.instagram_thread_id;
}

export default function InstagramSection() {
  const { setError, runAction } = useNotice();
  const [tab, setTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(true);

  const [queues, setQueues] = useState<IgQueueCounts>({});
  const [approvals, setApprovals] = useState<IgApproval[]>([]);
  const [threads, setThreads] = useState<IgThread[]>([]);
  const [comments, setComments] = useState<IgComment[]>([]);
  const [packs, setPacks] = useState<IgCuratorPack[]>([]);
  const [runs, setRuns] = useState<IgCuratorRun[]>([]);
  const [accounts, setAccounts] = useState<IgAccount[]>([]);
  const [actions, setActions] = useState<IgActionLog[]>([]);
  const [postStats, setPostStats] = useState<Record<number, IgPublicActionStat>>({});

  const load = useCallback(
    async (which: Tab) => {
      setLoading(true);
      try {
        if (which === "overview") {
          const [q, a, act] = await Promise.all([
            igApi.queues().then((r) => r.queues).catch(() => ({})),
            igApi.approvals("waiting", 50).then((r) => r.approvals).catch(() => []),
            igApi.actions(15).then((r) => r.actions).catch(() => []),
          ]);
          setQueues(q);
          setApprovals(a);
          setActions(act);
        } else if (which === "approvals") {
          setApprovals((await igApi.approvals("waiting", 100)).approvals);
        } else if (which === "threads") {
          setThreads((await igApi.threads(40)).threads);
        } else if (which === "comments") {
          setComments((await igApi.comments(40)).comments);
        } else if (which === "curator") {
          const [p, r] = await Promise.all([
            igApi.curatorPacks().then((x) => x.packs).catch(() => []),
            igApi.curatorRuns(undefined, 20).then((x) => x.runs).catch(() => []),
          ]);
          setPacks(p);
          setRuns(r);
        } else if (which === "accounts") {
          const [accs, stats] = await Promise.all([
            igApi.accounts(true).then((r) => r.accounts),
            igApi.publicActions().then((r) => r.accounts).catch(() => []),
          ]);
          setAccounts(accs);
          setPostStats(Object.fromEntries(stats.map((s) => [s.account_id, s])));
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load Instagram data");
      } finally {
        setLoading(false);
      }
    },
    [setError],
  );

  useEffect(() => {
    load(tab);
  }, [tab, load]);

  useVisibleInterval(
    () => {
      igApi.queues().then((r) => setQueues(r.queues)).catch(() => {});
    },
    tab === "overview" ? 10_000 : null,
  );

  async function review(id: number, decision: "approve" | "reject") {
    await runAction(async () => {
      await igApi.reviewApproval(id, decision);
      await load(tab === "overview" ? "overview" : "approvals");
      return `Approval #${id} ${decision}d`;
    }, `Approval #${id} ${decision}d`);
  }

  async function execute(id: number) {
    await runAction(async () => {
      const res = await igApi.executeApproval(id);
      await load(tab === "overview" ? "overview" : "approvals");
      return res?.error ? `Execute failed: ${res.error}` : `Executed approval #${id}`;
    }, `Executed approval #${id}`);
  }

  const totalApprovals = approvals.length;
  const totalQueued = Object.values(queues).reduce((a, b) => a + (b || 0), 0);

  return (
    <div className="space-y-5">
      <Card className="space-y-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold">Instagram</h2>
              <span className="rounded-full bg-pink-500/15 px-2 py-0.5 text-[11px] font-semibold uppercase text-pink-400 ring-1 ring-pink-500/20">
                Triage operator
              </span>
            </div>
            <p className="text-sm text-muted-foreground">
              DM &amp; comment triage with human-approval gating, plus curator
              feed-seeding. Runs as its own service; this view talks to it through
              the dashboard. Login &amp; advanced controls live in the{" "}
              <a
                href={IG_UI_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="text-pink-600 underline-offset-2 hover:underline"
              >
                full operator UI ↗
              </a>
              .
            </p>
          </div>
          <Button
            variant="secondary"
            onClick={() => runAction(async () => load(tab), "Refreshed")}
          >
            Refresh
          </Button>
        </div>

        <div className="flex flex-wrap gap-2">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium transition ${
                tab === t.key
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              }`}
            >
              {t.label}
              {t.key === "approvals" && totalApprovals > 0 && (
                <Badge
                  className={
                    tab === t.key ? "bg-white/20 text-white" : "bg-card text-foreground ring-1 ring-border"
                  }
                >
                  {totalApprovals}
                </Badge>
              )}
            </button>
          ))}
        </div>
      </Card>

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
      ) : tab === "overview" ? (
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card className="p-4">
              <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Pending approvals</div>
              <div className="mt-1 text-3xl font-semibold tracking-tight">{totalApprovals}</div>
            </Card>
            <Card className="p-4">
              <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Items in queues</div>
              <div className="mt-1 text-3xl font-semibold tracking-tight">{totalQueued}</div>
            </Card>
            <Card className="p-4 sm:col-span-2 lg:col-span-2">
              <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Queues</div>
              {Object.keys(queues).length === 0 ? (
                <div className="text-sm text-muted-foreground">No queued items.</div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {Object.entries(queues).map(([name, count]) => (
                    <span
                      key={name}
                      className="rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-foreground"
                    >
                      {name.replace(/_/g, " ")}: <span className="font-semibold">{count}</span>
                    </span>
                  ))}
                </div>
              )}
            </Card>
          </div>

          <Card className="p-4">
            <div className="mb-3 text-sm font-semibold">Recent actions</div>
            {actions.length === 0 ? (
              <div className="text-sm text-muted-foreground">No actions logged yet.</div>
            ) : (
              <div className="space-y-1.5">
                {actions.map((a) => (
                  <div key={a.id} className="flex items-center gap-2 text-sm">
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${a.success ? "bg-emerald-500" : "bg-rose-500"}`}
                    />
                    <span className="font-medium">{a.action_type}</span>
                    {a.error_message && <span className="text-rose-600">— {a.error_message}</span>}
                    <span className="ml-auto text-muted-foreground">{relativeTime(a.executed_at)}</span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      ) : tab === "approvals" ? (
        approvals.length === 0 ? (
          <Card className="p-8 text-center text-sm text-muted-foreground">
            No pending approvals. Drafted DMs/comments awaiting human sign-off appear here.
          </Card>
        ) : (
          <div className="space-y-3">
            {approvals.map((a) => (
              <Card key={a.id} className="space-y-3 p-4">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="font-mono text-muted-foreground">#{a.id}</span>
                  {a.action_type && (
                    <span className="rounded bg-muted px-1.5 py-0.5 font-medium text-foreground">
                      {a.action_type}
                    </span>
                  )}
                  {a.risk_level && (
                    <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${riskTone(a.risk_level)}`}>
                      risk: {a.risk_level}
                    </span>
                  )}
                  <span className="rounded-full bg-blue-500/15 px-2 py-0.5 text-[11px] font-medium text-blue-400 ring-1 ring-blue-500/20">
                    {a.status}
                  </span>
                  <span className="ml-auto text-muted-foreground">{relativeTime(a.created_at)}</span>
                </div>

                {a.proposed_text && (
                  <div className="rounded-md border border-border bg-card p-3 text-sm leading-snug whitespace-pre-wrap text-foreground">
                    {a.proposed_text}
                  </div>
                )}
                {a.target_id && (
                  <div className="text-xs text-muted-foreground">target: {a.target_id}</div>
                )}
                {a.risk_flags && a.risk_flags.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {a.risk_flags.map((f) => (
                      <span key={f} className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-400">
                        {f}
                      </span>
                    ))}
                  </div>
                )}

                <div className="flex flex-wrap gap-2">
                  {a.status === "waiting" && (
                    <>
                      <Button size="sm" onClick={() => review(a.id, "approve")}>
                        Approve
                      </Button>
                      <Button size="sm" variant="secondary" onClick={() => review(a.id, "reject")}>
                        Reject
                      </Button>
                    </>
                  )}
                  {a.status === "approved" && (
                    <Button size="sm" onClick={() => execute(a.id)}>
                      Execute
                    </Button>
                  )}
                </div>
              </Card>
            ))}
          </div>
        )
      ) : tab === "threads" ? (
        threads.length === 0 ? (
          <Card className="p-8 text-center text-sm text-muted-foreground">No DM threads ingested yet.</Card>
        ) : (
          <div className="space-y-2">
            {threads.map((t) => (
              <Card key={t.id} className="flex flex-wrap items-center gap-3 p-3">
                {!t.is_read && <span className="h-2 w-2 rounded-full bg-pink-500" title="unread" />}
                <span className="font-medium">{participantLabel(t)}</span>
                {t.priority_queue && (
                  <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                    {t.priority_queue.replace(/_/g, " ")}
                  </span>
                )}
                {t.unread_count > 0 && (
                  <Badge className="bg-pink-500/15 text-pink-400 ring-1 ring-pink-500/20">{t.unread_count} new</Badge>
                )}
                <span className="ml-auto text-xs text-muted-foreground">{relativeTime(t.last_message_at)}</span>
              </Card>
            ))}
          </div>
        )
      ) : tab === "comments" ? (
        comments.length === 0 ? (
          <Card className="p-8 text-center text-sm text-muted-foreground">No unreplied comments ingested yet.</Card>
        ) : (
          <div className="space-y-2">
            {comments.map((c) => (
              <Card key={c.id} className="space-y-1.5 p-3">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="font-medium text-foreground">@{c.username}</span>
                  {c.priority_queue && (
                    <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                      {c.priority_queue.replace(/_/g, " ")}
                    </span>
                  )}
                  {c.is_replied && (
                    <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] text-emerald-400 ring-1 ring-emerald-500/20">
                      replied
                    </span>
                  )}
                  <span className="ml-auto text-muted-foreground">{relativeTime(c.timestamp)}</span>
                </div>
                <div className="text-sm whitespace-pre-wrap text-foreground">{c.text}</div>
              </Card>
            ))}
          </div>
        )
      ) : tab === "curator" ? (
        <div className="space-y-5">
          <Card className="p-4">
            <div className="mb-3 text-sm font-semibold">Packs</div>
            {packs.length === 0 ? (
              <div className="text-sm text-muted-foreground">No curator packs configured.</div>
            ) : (
              <div className="space-y-2">
                {packs.map((p) => (
                  <div key={p.pack_id} className="flex flex-wrap items-center gap-2 rounded-md border border-border p-2.5 text-sm">
                    <span
                      className={`h-2 w-2 rounded-full ${p.enabled ? "bg-emerald-500" : "bg-muted-foreground/40"}`}
                      title={p.enabled ? "enabled" : "disabled"}
                    />
                    <span className="font-medium">{p.label || p.pack_id}</span>
                    <span className="text-xs text-muted-foreground">every {p.interval_minutes}m</span>
                    {p.allow_public_actions && (
                      <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-400">public actions</span>
                    )}
                    {p.last_status && (
                      <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                        {p.last_status}
                      </span>
                    )}
                    <span className="ml-auto text-xs text-muted-foreground">
                      {p.last_run_age || relativeTime(p.last_run_finished_at)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card className="p-4">
            <div className="mb-3 text-sm font-semibold">Recent runs</div>
            {runs.length === 0 ? (
              <div className="text-sm text-muted-foreground">No curator runs yet.</div>
            ) : (
              <div className="space-y-1.5">
                {runs.map((r) => (
                  <div key={r.id} className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="font-medium text-foreground">{r.pack_id}</span>
                    <span className="rounded bg-muted px-1.5 py-0.5 text-muted-foreground">{r.status}</span>
                    <span className="text-muted-foreground">
                      browse {r.browse_count} · like {r.like_count} · save {r.save_count} · follow {r.follow_count}
                    </span>
                    <span className="ml-auto text-muted-foreground">{relativeTime(r.started_at)}</span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      ) : (
        // accounts
        accounts.length === 0 ? (
          <Card className="p-8 text-center text-sm text-muted-foreground">
            No Instagram accounts yet. Add and log in accounts from the{" "}
            <a href={IG_UI_URL} target="_blank" rel="noopener noreferrer" className="text-pink-600 hover:underline">
              full operator UI ↗
            </a>
            .
          </Card>
        ) : (
          <div className="space-y-2">
            {accounts.map((acc) => {
              const st = postStats[acc.id];
              return (
                <Card key={acc.id} className="flex flex-wrap items-center gap-3 p-3">
                  <span
                    className={`h-2 w-2 rounded-full ${acc.is_logged_in ? "bg-emerald-500" : "bg-muted-foreground/40"}`}
                    title={acc.is_logged_in ? "logged in" : "not logged in"}
                  />
                  <span className="font-medium">@{acc.username}</span>
                  {!acc.enabled && (
                    <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">disabled</span>
                  )}
                  {acc.proxy_server && (
                    <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
                      {acc.proxy_server}
                    </span>
                  )}
                  {/* Posts = public actions (like+follow+comment) the account has
                      pushed through, against the ≤50/hr and ≤300/day caps. */}
                  {st && (
                    <span className="ml-auto flex items-center gap-2 text-xs">
                      <span
                        className={`rounded-md px-2 py-1 font-medium ${
                          st.hour_remaining === 0
                            ? "bg-rose-500/15 text-rose-400 ring-1 ring-rose-500/20"
                            : "bg-muted text-foreground"
                        }`}
                        title="Public actions in the last hour (cap 50)"
                      >
                        {st.posts_last_hour}/{st.hourly_cap} this hr
                      </span>
                      <span
                        className={`rounded-md px-2 py-1 font-medium ${
                          st.day_remaining === 0
                            ? "bg-rose-500/15 text-rose-400 ring-1 ring-rose-500/20"
                            : "bg-muted text-foreground"
                        }`}
                        title="Public actions in the last 24h (cap 300)"
                      >
                        {st.posts_last_day}/{st.daily_cap} today
                      </span>
                    </span>
                  )}
                </Card>
              );
            })}
          </div>
        )
      )}
    </div>
  );
}
