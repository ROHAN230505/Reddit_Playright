"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge, Button, Card, Skeleton } from "@/components/legacy-ui";
import { api, type RedditAccountItem, type ReplyItem } from "@/lib/api";
import { useVisibleInterval } from "@/lib/hooks/use-visible-interval";
import { useNotice } from "@/lib/notice-context";
import { RecentlyPostedPanel } from "@/components/recently-posted";
import { PostedAnalytics } from "@/components/posted-analytics";
import { GodlikeTabs } from "@/components/sections/shared";

type StatusTab = "QUEUED" | "POSTED";

const TAB_ORDER: StatusTab[] = ["QUEUED", "POSTED"];
const TAB_LABEL: Record<StatusTab, string> = { QUEUED: "Queued", POSTED: "Posted" };

// "Queued" aggregates every state that isn't posted yet, so nothing hides.
const QUEUED_STATUSES = ["PENDING", "APPROVED", "POSTING", "FAILED"];

function isPosted(status: string) {
  return status === "POSTED";
}

function statusTone(status: string): string {
  return isPosted(status)
    ? "bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/20"
    : "bg-blue-500/15 text-blue-400 ring-1 ring-blue-500/20";
}

function accountStatusTone(status: string): string {
  switch (status) {
    case "ACTIVE":
      return "bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/20";
    case "FAILED":
    case "NEEDS_REAUTH":
      return "bg-rose-500/15 text-rose-400 ring-1 ring-rose-500/20";
    case "DISABLED":
      return "bg-muted text-muted-foreground ring-1 ring-border";
    default:
      return "bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/20";
  }
}

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const now = Date.now();
  const then = new Date(iso).getTime();
  const seconds = Math.max(1, Math.round((now - then) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

async function fetchQueued(): Promise<ReplyItem[]> {
  const groups = await Promise.all(
    QUEUED_STATUSES.map((s) => api.replies(s, 200, undefined, "newest", 0, "glp")),
  );
  const merged = groups.flat();
  merged.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  return merged;
}

export default function GodlikeSection() {
  const { setError, runAction } = useNotice();
  const [tab, setTab] = useState<StatusTab>("POSTED");
  const [replies, setReplies] = useState<ReplyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draftText, setDraftText] = useState<string>("");
  const [autoApprove, setAutoApprove] = useState<boolean | null>(null);
  const [topics, setTopics] = useState<string[]>([]);
  const [accounts, setAccounts] = useState<RedditAccountItem[]>([]);
  const [counts, setCounts] = useState<Record<StatusTab, number>>({
    QUEUED: 0,
    POSTED: 0,
  });

  const load = useCallback(
    async (status: StatusTab) => {
      setLoading(true);
      try {
        const rows =
          status === "POSTED"
            ? await api.replies("POSTED", 400, undefined, "newest", 0, "glp")
            : await fetchQueued();
        setReplies(rows);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load GLP replies");
      } finally {
        setLoading(false);
      }
    },
    [setError],
  );

  const refreshCounts = useCallback(async () => {
    try {
      const { counts: queueCounts } = await api.workerQueue("glp");
      setCounts({
        QUEUED:
          (queueCounts.PENDING ?? 0) +
          (queueCounts.APPROVED ?? 0) +
          (queueCounts.POSTING ?? 0) +
          (queueCounts.FAILED ?? 0),
        POSTED: queueCounts.POSTED ?? 0,
      });
    } catch {
      // counts are best-effort; ignore transient errors
    }
  }, []);

  useEffect(() => {
    load(tab);
  }, [tab, load]);

  useEffect(() => {
    void refreshCounts();
  }, [refreshCounts]);

  useVisibleInterval(() => {
    void refreshCounts();
  }, 15_000);

  useEffect(() => {
    // One-shot read of the backend's auto-approve flag + scraped topics so the
    // UI can show whether new drafts skip review and which forums we target.
    api
      .glpConfig()
      .then((cfg) => {
        setAutoApprove(cfg.auto_approve);
        setTopics(cfg.topics ?? []);
      })
      .catch(() => setAutoApprove(null));
  }, []);

  // Load the GLP accounts so the operator can see which accounts are wired up
  // and what forum sections they're scoped to.
  const loadAccounts = useCallback(async () => {
    try {
      const all = await api.accounts();
      setAccounts(all.filter((a) => a.platform === "glp"));
    } catch {
      // best-effort; the accounts panel just stays empty on error
    }
  }, []);

  useEffect(() => {
    loadAccounts();
  }, [loadAccounts]);

  async function triggerScrape() {
    await runAction(async () => {
      const r = await api.triggerGlpScrape(30);
      await Promise.all([load(tab), refreshCounts()]);
      return `Scrape queued (task ${r.task_id})`;
    }, "Scrape queued");
  }

  async function setStatus(replyId: number, status: string) {
    await runAction(async () => {
      await api.updateReply(replyId, { status });
      await Promise.all([load(tab), refreshCounts()]);
    }, `Reply #${replyId} → ${status}`);
  }

  async function saveEdit(replyId: number) {
    const text = draftText.trim();
    if (!text) {
      setError("Reply text cannot be blank");
      return;
    }
    await runAction(async () => {
      await api.updateReply(replyId, { reply_text: text });
      setEditingId(null);
      setDraftText("");
      await load(tab);
    }, `Reply #${replyId} updated`);
  }

  const sections = useMemo(
    () => (
      <div className="space-y-3">
        {replies.map((reply) => {
          const isEditing = editingId === reply.reply_id;
          const posted = isPosted(reply.status);
          return (
            <Card key={reply.reply_id} className="space-y-3 p-4">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="font-mono text-muted-foreground">#{reply.reply_id}</span>
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${statusTone(reply.status)}`}>
                  {posted ? "Posted" : "Queued"}
                </span>
                <span className="rounded bg-violet-500/15 px-1.5 py-0.5 font-mono text-[10px] text-violet-400">
                  glp/{reply.platform_section ?? "forum"}
                </span>
                {reply.includes_promo && (
                  <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] font-medium text-amber-400 ring-1 ring-amber-500/20">
                    promo
                  </span>
                )}
                <span className="text-muted-foreground">{relativeTime(reply.created_at)}</span>
                {reply.posted_at && (
                  <span className="text-muted-foreground" title={reply.posted_at}>
                    posted {relativeTime(reply.posted_at)}
                  </span>
                )}
                {reply.target_url && (
                  <a
                    href={reply.target_url}
                    target="_blank"
                    rel="noreferrer"
                    className="ml-auto text-xs text-primary underline-offset-2 hover:underline"
                  >
                    Open thread ↗
                  </a>
                )}
              </div>

              <div className="rounded-md bg-muted p-3 text-sm text-foreground">
                <div className="mb-1 text-xs font-semibold uppercase text-muted-foreground">
                  In reply to {reply.comment_author ? `@${reply.comment_author}` : "the OP"}
                </div>
                <div className="line-clamp-4 whitespace-pre-wrap">{reply.comment_text}</div>
              </div>

              {isEditing ? (
                <div className="space-y-2">
                  <textarea
                    value={draftText}
                    onChange={(e) => setDraftText(e.target.value)}
                    className="min-h-[100px] w-full rounded-md border border-border bg-card p-2 text-sm text-foreground"
                  />
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => saveEdit(reply.reply_id)}>
                      Save
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        setEditingId(null);
                        setDraftText("");
                      }}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="rounded-md border border-border bg-card p-3 text-sm leading-snug text-foreground">
                  {reply.reply_text}
                </div>
              )}

              {reply.posting_error && (
                <div className="rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-400">
                  {reply.posting_error}
                </div>
              )}

              {!posted && (
                <div className="flex flex-wrap gap-2">
                  {reply.status === "FAILED" && (
                    <Button size="sm" onClick={() => setStatus(reply.reply_id, "APPROVED")}>
                      Retry (requeue)
                    </Button>
                  )}
                  {!isEditing && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setEditingId(reply.reply_id);
                        setDraftText(reply.reply_text);
                      }}
                    >
                      Edit text
                    </Button>
                  )}
                </div>
              )}
            </Card>
          );
        })}
      </div>
    ),
    [replies, editingId, draftText],
  );

  return (
    <div className="space-y-5">
      <GodlikeTabs />
      <Card className="space-y-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold">Godlike Productions</h2>
              {autoApprove === true && (
                <span
                  className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-semibold uppercase text-emerald-400 ring-1 ring-emerald-500/20"
                  title="GLP drafts queue automatically. The Playwright worker (with a GLP account assigned) auto-claims and posts them."
                >
                  Auto-post: ON
                </span>
              )}
            </div>
            <p className="text-sm text-muted-foreground">
              AI-generated GLP forum replies promoting the active brand, scoped to
              tech/AI threads only. Reading is anonymous; posting requires a
              logged-in GLP account on a residential proxy. New drafts queue
              automatically and the Playwright worker posts them — operator can
              still edit from here.
            </p>
            {topics.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                <span className="font-semibold uppercase text-muted-foreground">Targeting</span>
                {topics.map((t) => (
                  <span
                    key={t}
                    className="rounded bg-violet-500/15 px-1.5 py-0.5 font-mono text-[10px] text-violet-400"
                    title={`Scraping https://www.godlikeproductions.com/topics/${t}`}
                  >
                    {t}
                  </span>
                ))}
                <span className="text-muted-foreground">(GLP has no dedicated AI forum)</span>
              </div>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={triggerScrape}>Run scrape now</Button>
            <Button
              variant="secondary"
              onClick={() =>
                runAction(async () => {
                  await load(tab);
                  await refreshCounts();
                }, "Refreshed")
              }
            >
              Refresh
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {TAB_ORDER.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setTab(s)}
              className={`flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium transition ${
                tab === s
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              }`}
            >
              {TAB_LABEL[s]}
              <Badge
                className={
                  tab === s
                    ? "bg-white/20 text-white"
                    : "bg-card text-foreground ring-1 ring-border"
                }
              >
                {counts[s]}
              </Badge>
            </button>
          ))}
        </div>
      </Card>

      {accounts.length > 0 && (
        <Card className="space-y-3 p-5">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">GLP accounts ({accounts.length})</h3>
            <span className="text-xs text-muted-foreground">
              Worker posts only on these · cadence 2/hr · 12/day
            </span>
          </div>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {accounts.map((acc) => (
              <div
                key={acc.id}
                className="flex flex-col gap-1.5 rounded-md border border-border bg-card p-3 text-xs"
              >
                <div className="flex items-center gap-2">
                  <span className="font-mono font-medium text-foreground">{acc.username}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${accountStatusTone(acc.status)}`}>
                    {acc.status}
                  </span>
                  {!acc.is_enabled && (
                    <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
                      disabled
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-1">
                  <span className="font-semibold uppercase text-muted-foreground">Forums</span>
                  {acc.assigned_sections && acc.assigned_sections.length > 0 ? (
                    acc.assigned_sections.map((s) => (
                      <span
                        key={s}
                        className="rounded bg-violet-500/15 px-1.5 py-0.5 font-mono text-[10px] text-violet-400"
                      >
                        {s}
                      </span>
                    ))
                  ) : (
                    <span className="text-muted-foreground">all (unscoped)</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
      ) : tab === "POSTED" ? (
        <div className="space-y-5">
          <PostedAnalytics posted={replies} groupLabel="Top forums" groupMode="forum" barClass="bg-violet-400" />
          <RecentlyPostedPanel posted={replies} subtitle="Godlike · newest first" />
        </div>
      ) : replies.length === 0 ? (
        <Card className="p-8 text-center text-sm text-muted-foreground">
          <span className="block">
            No queued GLP replies. New drafts queue here for the Playwright
            worker. The Celery beat scrapes every 15 minutes, or click{" "}
            <em>Run scrape now</em> above.
          </span>
          <span className="mt-3 block text-xs text-amber-400">
            Empty? Unlike Reddit (hosted Apify API), GLP scraping needs
            Playwright + a residential proxy (<code className="rounded bg-muted px-1">GLP_PROXY_URL</code>)
            to get past Cloudflare. If those aren&apos;t configured the
            scheduled scrape fails — check the Logs / scrape-runs for the error.
          </span>
        </Card>
      ) : (
        sections
      )}
    </div>
  );
}
