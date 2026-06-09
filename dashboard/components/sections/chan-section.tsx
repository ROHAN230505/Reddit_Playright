"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge, Button, Card, Skeleton } from "@/components/ui";
import { api, type ReplyItem } from "@/lib/api";
import { useNotice } from "@/lib/notice-context";
import { RecentlyPostedPanel } from "@/components/recently-posted";
import { PostedAnalytics } from "@/components/posted-analytics";

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
    ? "bg-teal-50 text-teal-700 ring-1 ring-teal-200"
    : "bg-blue-50 text-blue-700 ring-1 ring-blue-200";
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
    QUEUED_STATUSES.map((s) => api.replies(s, 200, undefined, "newest", 0, "chan")),
  );
  const merged = groups.flat();
  merged.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  return merged;
}

export default function ChanSection() {
  const { setError, runAction } = useNotice();
  const [tab, setTab] = useState<StatusTab>("POSTED");
  const [replies, setReplies] = useState<ReplyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draftText, setDraftText] = useState<string>("");
  const [config, setConfig] = useState<{
    auto_approve: boolean;
    boards: string[];
    threads_per_board: number;
  } | null>(null);
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
            ? await api.replies("POSTED", 2000, undefined, "newest", 0, "chan")
            : await fetchQueued();
        setReplies(rows);
        if (status === "POSTED") {
          setCounts((c) => ({ ...c, POSTED: rows.length }));
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load 4chan replies");
      } finally {
        setLoading(false);
      }
    },
    [setError],
  );

  // Queued is small and changes as the worker posts — poll it frequently.
  const refreshCounts = useCallback(async () => {
    try {
      const queued = await fetchQueued().then((r) => r.length);
      setCounts((c) => ({ ...c, QUEUED: queued }));
    } catch {
      // counts best-effort
    }
  }, []);

  // Posted grows slowly — fetch the count on mount (load("POSTED") keeps it
  // fresh while viewing) rather than re-pulling the full set every few seconds.
  const refreshPostedCount = useCallback(async () => {
    try {
      const rows = await api.replies("POSTED", 2000, undefined, "newest", 0, "chan");
      setCounts((c) => ({ ...c, POSTED: rows.length }));
    } catch {
      // best-effort
    }
  }, []);

  useEffect(() => {
    load(tab);
  }, [tab, load]);

  useEffect(() => {
    refreshCounts();
    refreshPostedCount();
    const timer = window.setInterval(refreshCounts, 8000);
    return () => window.clearInterval(timer);
  }, [refreshCounts, refreshPostedCount]);

  useEffect(() => {
    api
      .chanConfig()
      .then(setConfig)
      .catch(() => setConfig(null));
  }, []);

  async function triggerScrape() {
    await runAction(async () => {
      const r = await api.triggerChanScrape();
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
          const board = reply.platform_section ?? reply.subreddit ?? "unknown";
          const posted = isPosted(reply.status);
          return (
            <Card key={reply.reply_id} className="space-y-3 p-4">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="font-mono text-slate-500">#{reply.reply_id}</span>
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${statusTone(reply.status)}`}>
                  {posted ? "Posted" : "Queued"}
                </span>
                <span className="rounded bg-emerald-100 px-1.5 py-0.5 font-mono text-[10px] text-emerald-700">
                  /{board}/
                </span>
                {reply.includes_promo && (
                  <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700 ring-1 ring-amber-200">
                    sentx.ai promo
                  </span>
                )}
                <span className="text-muted">{relativeTime(reply.created_at)}</span>
                {reply.posted_at && (
                  <span className="text-muted" title={reply.posted_at}>
                    posted {relativeTime(reply.posted_at)}
                  </span>
                )}
                {reply.target_url && (
                  <a
                    href={reply.target_url}
                    target="_blank"
                    rel="noreferrer"
                    className="ml-auto text-xs text-blue-600 underline-offset-2 hover:underline"
                  >
                    Open thread ↗
                  </a>
                )}
              </div>

              <div className="rounded-md bg-slate-50 p-3 text-sm text-slate-700">
                <div className="mb-1 text-xs font-semibold uppercase text-muted">
                  In reply to {reply.comment_author ? reply.comment_author : "the OP"}
                </div>
                <div className="line-clamp-4 whitespace-pre-wrap">{reply.comment_text}</div>
              </div>

              {isEditing ? (
                <div className="space-y-2">
                  <textarea
                    value={draftText}
                    onChange={(e) => setDraftText(e.target.value)}
                    className="min-h-[100px] w-full rounded-md border border-border bg-white p-2 text-sm"
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
                <div className="rounded-md border border-slate-200 bg-white p-3 font-mono text-sm leading-snug whitespace-pre-wrap">
                  {reply.reply_text}
                </div>
              )}

              {reply.posting_error && (
                <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
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
      <Card className="space-y-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold">4chan</h2>
              {config?.auto_approve === true && (
                <span
                  className="rounded-full bg-teal-50 px-2 py-0.5 text-[11px] font-semibold uppercase text-accent ring-1 ring-teal-200"
                  title="4chan drafts queue automatically. The Playwright worker (with a chan account assigned) auto-claims and posts them."
                >
                  Auto-post: ON
                </span>
              )}
              {config?.boards && (
                <span className="text-xs text-muted">
                  boards:{" "}
                  {config.boards.map((b) => (
                    <span key={b} className="ml-1 rounded bg-emerald-100 px-1.5 py-0.5 font-mono text-[10px] text-emerald-700">
                      /{b}/
                    </span>
                  ))}
                </span>
              )}
            </div>
            <p className="text-sm text-muted">
              AI-generated 4chan replies promoting sentx.ai. Reading uses the
              public JSON API (no proxy needed for ingest); posting needs a
              Playwright worker — install a 4chan Pass cookie to skip per-post
              captchas. Drafts queue automatically; operator can still edit.
            </p>
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
                  ? "bg-slate-900 text-white"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
            >
              {TAB_LABEL[s]}
              <Badge
                className={
                  tab === s
                    ? "bg-white/20 text-white"
                    : "bg-white text-slate-700 ring-1 ring-slate-300"
                }
              >
                {counts[s]}
              </Badge>
            </button>
          ))}
        </div>
      </Card>

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
      ) : tab === "POSTED" ? (
        <div className="space-y-5">
          <PostedAnalytics posted={replies} groupLabel="Top boards" groupMode="board" barClass="bg-emerald-400" />
          <RecentlyPostedPanel posted={replies} subtitle="4chan · newest first" />
        </div>
      ) : replies.length === 0 ? (
        <Card className="p-8 text-center text-sm text-muted">
          No queued 4chan replies. Everything auto-posts — new drafts queue here
          briefly, then the worker posts them. The Celery beat scrapes every 5
          minutes, or click <em>Run scrape now</em> above.
        </Card>
      ) : (
        sections
      )}
    </div>
  );
}
