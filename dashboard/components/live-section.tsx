"use client";

import { useEffect, useRef, useState } from "react";
import { api, type AccountActivity, type RedditAccountItem } from "@/lib/api";
import { Badge, Button, Card } from "@/components/ui";

function relativeTime(value: string | null): string {
  if (!value) return "n/a";
  const diff = Math.floor((Date.now() - new Date(value).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function formatCountdown(secs: number): string {
  if (secs <= 0) return "ready";
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return m > 0 ? `${m}:${String(s).padStart(2, "0")} remaining` : `${s}s remaining`;
}

function statusColor(status: RedditAccountItem["status"]): string {
  switch (status) {
    case "ACTIVE": return "bg-emerald-500";
    case "VERIFYING":
    case "NEW":
    case "NEEDS_REAUTH": return "bg-amber-500";
    case "FAILED": return "bg-rose-500";
    default: return "bg-zinc-400";
  }
}

function statusPillClass(status: RedditAccountItem["status"]): string {
  switch (status) {
    case "ACTIVE": return "bg-emerald-500/15 text-emerald-700 border-emerald-200";
    case "VERIFYING":
    case "NEW":
    case "NEEDS_REAUTH": return "bg-amber-500/15 text-amber-700 border-amber-200";
    case "FAILED": return "bg-rose-500/15 text-rose-700 border-rose-200";
    default: return "bg-zinc-500/15 text-zinc-600 border-zinc-200";
  }
}

function UsageBar({ used, limit, atLimit }: { used: number; limit: number; atLimit: boolean }) {
  const segments = 30;
  const safeLimit = Math.max(1, limit);
  const filled = Math.min(segments, Math.round((Math.min(used, safeLimit) / safeLimit) * segments));
  const empty = segments - filled;
  const cellColor = atLimit ? "bg-rose-400" : "bg-emerald-500";
  return (
    <span className="grid w-full max-w-[360px] grid-cols-[repeat(30,minmax(0,1fr))] gap-0.5 align-middle">
      {Array.from({ length: filled }, (_, i) => (
        <span key={`f-${i}`} className={`h-3 min-w-0 rounded-sm ${cellColor}`} />
      ))}
      {Array.from({ length: empty }, (_, i) => (
        <span key={`e-${i}`} className="h-3 min-w-0 rounded-sm bg-slate-200" />
      ))}
    </span>
  );
}

function ActivityPanel({
  account,
  activity,
  onReverify,
}: {
  account: RedditAccountItem;
  activity: AccountActivity | null;
  onReverify: () => void;
}) {
  const [countdown, setCountdown] = useState(0);
  const tickRef = useRef<number | null>(null);

  function startCountdownTick(secs: number) {
    if (tickRef.current) window.clearInterval(tickRef.current);
    setCountdown(Math.max(0, secs));
    if (secs <= 0) return;
    tickRef.current = window.setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          if (tickRef.current) window.clearInterval(tickRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }

  useEffect(() => {
    startCountdownTick(activity?.seconds_until_eligible ?? 0);
    return () => {
      if (tickRef.current) window.clearInterval(tickRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [account.id, activity?.seconds_until_eligible]);

  const inCooldown = activity?.is_in_cooldown ?? false;

  return (
    <Card className="min-w-0 overflow-hidden p-5">
      {/* Header row */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`inline-block h-3 w-3 rounded-full ${statusColor(account.status)}`} />
          <Badge className={`text-sm px-3 py-1 ${statusPillClass(account.status)}`}>
            {account.status}
          </Badge>
          <span className="font-semibold">u/{account.username}</span>
          {account.profile_index != null && (
            <span
              className="font-mono text-xs text-slate-500"
              title={account.profile_summary ?? undefined}
            >
              slot {account.profile_index}
            </span>
          )}
        </div>
        <Button size="sm" variant="secondary" onClick={onReverify}>
          Reverify
        </Button>
      </div>

      {/* Proxy */}
      <div className="mt-2 text-sm text-muted">
        <span className="font-semibold text-slate-600">proxy:</span>{" "}
        {account.proxy_label ?? <span className="italic">none</span>}
      </div>

      {!activity && (
        <div className="mt-4 text-sm text-muted italic">Activity loading...</div>
      )}

      {/* Usage bars */}
      {activity && (
        <>
          <div className="mt-4 grid gap-3 text-sm">
            <div className="grid min-w-0 grid-cols-[120px_minmax(0,360px)_auto] items-center gap-3">
              <span className="text-muted">Posts last hour</span>
              <UsageBar
                used={activity.posts_last_hour}
                limit={activity.posts_per_hour_limit}
                atLimit={activity.is_at_hourly_limit}
              />
              <span className="whitespace-nowrap font-mono text-xs text-slate-600">
                {activity.posts_last_hour} / {activity.posts_per_hour_limit}
              </span>
            </div>
            <div className="grid min-w-0 grid-cols-[120px_minmax(0,360px)_auto] items-center gap-3">
              <span className="text-muted">Posts last day</span>
              <UsageBar
                used={activity.posts_last_day}
                limit={activity.posts_per_day_limit}
                atLimit={activity.is_at_daily_limit}
              />
              <span className="whitespace-nowrap font-mono text-xs text-slate-600">
                {activity.posts_last_day} / {activity.posts_per_day_limit}
              </span>
            </div>
          </div>

          {/* Cooldown */}
          <div className="mt-3 text-sm">
            <span className="text-muted">Last posted:</span>{" "}
            {relativeTime(activity.last_posted_at)}
          </div>
          <div className="mt-1 text-sm">
            <span className="text-muted">Cooldown:</span>{" "}
            {inCooldown && countdown > 0 ? (
              <span className="text-amber-600">
                {formatCountdown(countdown)} &#x23F1;
              </span>
            ) : (
              <span className="text-emerald-600">ready ✓</span>
            )}
          </div>

          {/* Recent posts */}
          <div className="mt-4">
            <div className="mb-1 text-xs font-semibold uppercase text-muted">
              Recent posts ({Math.min(activity.recent_posts.length, 5)} most recent)
            </div>
            {activity.recent_posts.length === 0 ? (
              <div className="text-sm text-muted italic">No posts yet</div>
            ) : (
              <ul className="space-y-1">
                {activity.recent_posts.slice(0, 5).map((post) => (
                  <li key={post.reply_id} className="text-sm">
                    <span className="text-muted">{relativeTime(post.posted_at)}</span>
                    {post.subreddit && (
                      <> · <span className="font-medium">r/{post.subreddit}</span></>
                    )}
                    {" · "}
                    {post.target_url ? (
                      <a
                        href={post.target_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-accent underline hover:no-underline"
                        title={post.reply_text_preview}
                      >
                        &ldquo;{post.reply_text_preview.slice(0, 60)}{post.reply_text_preview.length > 60 ? "…" : ""}&rdquo;
                      </a>
                    ) : (
                      <span className="text-slate-600" title={post.reply_text_preview}>
                        &ldquo;{post.reply_text_preview.slice(0, 60)}{post.reply_text_preview.length > 60 ? "…" : ""}&rdquo;
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}

      {/* Last error */}
      {account.last_error && (
        <Card className="mt-4 border-rose-200 bg-rose-50 p-3">
          <div className="mb-1 text-xs font-semibold uppercase text-danger">Last error</div>
          <pre className="whitespace-pre-wrap text-sm text-danger">{account.last_error}</pre>
        </Card>
      )}
    </Card>
  );
}

export default function LiveSection({ onGoToAccounts }: { onGoToAccounts: () => void }) {
  const [accounts, setAccounts] = useState<RedditAccountItem[]>([]);
  const [activityByAccount, setActivityByAccount] = useState<Record<number, AccountActivity>>({});
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  async function load() {
    try {
      const data = await api.accountsHealth();
      setAccounts(data.accounts);
      setActivityByAccount(data.activity);
      setSelectedId((prev) => {
        if (prev !== null) return prev;
        const first = data.accounts.find((a) => a.is_enabled);
        return first ? first.id : null;
      });
    } catch {
      // silently ignore
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 5000);
    return () => window.clearInterval(timer);
  }, []);

  const enabledAccounts = accounts.filter((a) => a.is_enabled);
  const selected = accounts.find((a) => a.id === selectedId) ?? null;

  async function handleReverify() {
    if (!selected) return;
    try {
      await api.reverifyAccount(selected.id);
      await load();
    } catch (err) {
      console.error(err);
    }
  }

  if (!loading && enabledAccounts.length === 0) {
    return (
      <Card className="p-8 text-center">
        <div className="text-sm font-medium text-slate-800">No enabled accounts</div>
        <div className="mt-1 text-sm text-muted">
          Go to the{" "}
          <button className="font-medium text-accent underline" onClick={onGoToAccounts}>
            Settings / Accounts
          </button>{" "}
          to add and enable Reddit accounts.
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold">Live Account Status</h2>
        <p className="text-sm text-muted">Real-time view of each enabled Reddit account. Activity polls every 5s; cooldown ticks every 1s.</p>
      </div>

      {/* Sub-tab bar */}
      {enabledAccounts.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {enabledAccounts.map((account) => (
            <button
              key={account.id}
              onClick={() => setSelectedId(account.id)}
              className={`flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm font-medium transition-colors ${
                selectedId === account.id
                  ? "border-slate-900 bg-slate-900 text-white"
                  : "border-border bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              <span className={`inline-block h-2 w-2 rounded-full ${statusColor(account.status)}`} />
              {account.username}
            </button>
          ))}
        </div>
      )}

      {/* Activity panel */}
      {selected && (
        <ActivityPanel
          key={selected.id}
          account={selected}
          activity={activityByAccount[selected.id] ?? null}
          onReverify={handleReverify}
        />
      )}

      {loading && !selected && (
        <div className="text-sm text-muted">Loading accounts…</div>
      )}
    </div>
  );
}
