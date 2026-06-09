"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type AccountActivity,
  type RedditAccountItem,
  type ReplyItem,
} from "@/lib/api";
import { Button, Card, Input, Textarea } from "@/components/ui";
import { useNotice } from "@/lib/notice-context";
import { EmptyState, RepliesTabs } from "@/components/sections/shared";

const MIN_SLOT_COUNT = 6;
const POLL_MS = 15000;
const PENDING_FETCH_LIMIT = 500;
// When one sub accounts for >SWAMPED_THRESHOLD of an account's unused PENDING
// pool, the slot picker also considers replies from subs OUTSIDE the account's
// assigned_subreddits — so the operator isn't stuck cycling through a single
// dominant sub when a generation burst skewed the queue.
const SWAMPED_THRESHOLD = 0.5;

// Keep this in sync with the regex in backend/app/schemas.py — both reject the
// same URLs so the button stays in lockstep with what the API will accept.
// Accepts the canonical /comments/ form AND /r/<sub>/s/<shortcode> share links
// (Reddit's mobile/share UI issues these; they redirect to a comment permalink).
const REDDIT_COMMENT_URL_RE =
  /^https?:\/\/(?:[\w-]+\.)?reddit\.com\/(?:.*?\/comments\/[A-Za-z0-9_-]+|(?:r\/[\w-]+\/)?s\/[A-Za-z0-9_-]+)/i;

function isValidRedditCommentUrl(value: string): boolean {
  return REDDIT_COMMENT_URL_RE.test(value.trim());
}

type SlotState =
  | { kind: "active" }
  | { kind: "cooldown"; secondsLeft: number }
  | { kind: "hourly"; used: number; cap: number; resetsInSeconds: number }
  | { kind: "daily"; used: number; cap: number; resetsInSeconds: number }
  | { kind: "disabled" };

function AssignedSubsBadge({ subs }: { subs: string[] }) {
  if (!subs.length) {
    return (
      <span
        className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-500"
        title="No subreddits assigned — this slot pulls from the full pending pool. Click 'Auto-assign subreddits' to balance the workload."
      >
        any sub
      </span>
    );
  }
  const preview = subs.slice(0, 2).join(", ");
  const more = subs.length > 2 ? ` +${subs.length - 2}` : "";
  return (
    <span
      className="inline-flex max-w-[260px] items-center truncate rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-medium text-indigo-700 ring-1 ring-indigo-200"
      title={subs.join(", ")}
    >
      {preview}
      {more}
    </span>
  );
}

// Backend returns naive datetimes (no TZ suffix) from datetime.utcnow().
// Browsers parse those as LOCAL time, which silently breaks countdowns
// for any timezone other than UTC. Force UTC interpretation.
function parseServerUtc(value: string): number {
  if (/Z$/.test(value) || /[+-]\d{2}:?\d{2}$/.test(value)) {
    return new Date(value).getTime();
  }
  return new Date(value + "Z").getTime();
}

function formatCountdown(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60);
  const ss = (s % 60).toString().padStart(2, "0");
  if (m >= 60) {
    const h = Math.floor(m / 60);
    const mm = (m % 60).toString().padStart(2, "0");
    return `${h}:${mm}:${ss}`;
  }
  return `${m}:${ss}`;
}

function deriveSlotState(
  account: RedditAccountItem,
  activity: AccountActivity | undefined,
  nowMs: number,
): SlotState {
  if (!account.is_enabled) return { kind: "disabled" };
  if (!activity) return { kind: "active" };
  if (activity.is_in_cooldown && activity.next_eligible_at) {
    const target = parseServerUtc(activity.next_eligible_at);
    const secondsLeft = Math.max(0, Math.round((target - nowMs) / 1000));
    if (secondsLeft > 0) return { kind: "cooldown", secondsLeft };
  }
  if (activity.is_at_hourly_limit) {
    // Window resets when the oldest post-in-the-last-hour ages past 60min.
    // We don't know exactly, so estimate from last_posted_at if recent.
    const lastPosted = activity.recent_posts.find((p) => p.posted_at);
    const reference = lastPosted?.posted_at
      ? parseServerUtc(lastPosted.posted_at)
      : nowMs;
    const resetsInSeconds = Math.max(
      0,
      Math.round((reference + 60 * 60 * 1000 - nowMs) / 1000),
    );
    return {
      kind: "hourly",
      used: activity.posts_last_hour,
      cap: activity.posts_per_hour_limit,
      resetsInSeconds,
    };
  }
  if (activity.is_at_daily_limit) {
    const oldestInDay = activity.recent_posts
      .filter((p) => p.posted_at)
      .map((p) => parseServerUtc(p.posted_at!))
      .sort((a, b) => a - b)[0];
    const reference = oldestInDay ?? nowMs;
    const resetsInSeconds = Math.max(
      0,
      Math.round((reference + 24 * 60 * 60 * 1000 - nowMs) / 1000),
    );
    return {
      kind: "daily",
      used: activity.posts_last_day,
      cap: activity.posts_per_day_limit,
      resetsInSeconds,
    };
  }
  return { kind: "active" };
}

export default function RepliesLiveSection() {
  const { runAction, busy } = useNotice();
  const [accounts, setAccounts] = useState<RedditAccountItem[]>([]);
  const [pending, setPending] = useState<ReplyItem[]>([]);
  const [activity, setActivity] = useState<Record<number, AccountActivity>>({});
  const [nowMs, setNowMs] = useState<number>(() => Date.now());
  const [edits, setEdits] = useState<Record<number, string>>({});
  const [postedUrls, setPostedUrls] = useState<Record<number, string>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  // Use a ref to avoid effect dependency on edits.
  const editsRef = useRef(edits);
  editsRef.current = edits;

  const loadAccountsHealth = useCallback(async () => {
    const health = await api.accountsHealth();
    setAccounts(health.accounts);
    setActivity(health.activity);
    setLoadError(null);
    return health.accounts;
  }, []);

  const loadPending = useCallback(async () => {
    // Newest first so a flood of high-upvote replies in one subreddit (e.g.
    // r/technology) doesn't drown out smaller subs in the window.
    // min_promo=200 enforces a floor of promo replies in the visible pool —
    // if the recent window is mostly normals, older promos are pulled forward
    // to maintain the floor.
    const items = await api.replies(
      "PENDING",
      PENDING_FETCH_LIMIT,
      undefined,
      "newest",
      200,
    );
    setPending(items);
    setLoadError(null);
  }, []);

  // Initial fetch.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await loadAccountsHealth();
        await loadPending();
        if (cancelled) return;
        setLoadError(null);
        setHasLoadedOnce(true);
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : "Failed to load");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadAccountsHealth, loadPending]);

  // Periodic poll for activity + pending.
  useEffect(() => {
    const timer = window.setInterval(() => {
      loadAccountsHealth().catch((err) =>
        setLoadError(err instanceof Error ? err.message : String(err)),
      );
      loadPending().catch((err) =>
        setLoadError(err instanceof Error ? err.message : String(err)),
      );
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [loadAccountsHealth, loadPending]);

  // 1s tick for countdowns.
  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  // Build slot assignments: for each profile_index, pick the enabled
  // account at that slot (lowest id wins on collision), then assign the
  // next-newest unused PENDING reply that matches the account's
  // assigned_subreddits filter (if set). When assigned_subreddits is empty,
  // the slot draws from the full pool.
  const slots = useMemo(() => {
    const slotCount = Math.max(
      MIN_SLOT_COUNT,
      ...accounts.map((a) => (a.profile_index ?? 0) + 1),
    );
    // Sort: enabled first, then by id ascending. So if two accounts share a
    // profile_index, the enabled one wins the slot — fixes the case where a
    // disabled (FAILED) account hides an active sibling at the same slot.
    const accountBySlot = new Map<number, RedditAccountItem>();
    const sorted = [...accounts].sort((a, b) => {
      if (a.is_enabled !== b.is_enabled) return a.is_enabled ? -1 : 1;
      return a.id - b.id;
    });
    for (const acc of sorted) {
      const slot = Math.max(0, Math.min(slotCount - 1, acc.profile_index ?? 0));
      if (!accountBySlot.has(slot)) accountBySlot.set(slot, acc);
    }
    // Union of subs owned by ANY enabled account. Used inside Tier 2 (swamp
    // escape) to prefer truly orphan subs over subs that belong to other
    // active accounts — keeps brand isolation as strong as possible while
    // still letting a swamped account pick from outside its own filter.
    const allAssignedSubs = new Set<string>();
    for (const acc of accounts) {
      if (!acc.is_enabled) continue;
      for (const s of acc.assigned_subreddits ?? []) {
        const lower = s.toLowerCase();
        if (lower) allAssignedSubs.add(lower);
      }
    }
    const usedReplyIds = new Set<number>();
    const result: {
      slot: number;
      account: RedditAccountItem | null;
      reply: ReplyItem | null;
      state: SlotState;
    }[] = [];
    for (let slot = 0; slot < slotCount; slot++) {
      const account = accountBySlot.get(slot) ?? null;
      let reply: ReplyItem | null = null;
      if (account && account.is_enabled) {
        const subFilter = (account.assigned_subreddits ?? [])
          .map((s) => s.toLowerCase())
          .filter(Boolean);
        if (subFilter.length === 0) {
          // No filter: just take newest unused.
          const next = pending.find((r) => !usedReplyIds.has(r.reply_id));
          if (next) {
            reply = next;
            usedReplyIds.add(next.reply_id);
          }
        } else {
          // Sub-aware pick: rank candidate subs by how recently the account
          // last posted to each (stalest first, never-posted-to wins over
          // everything). Then return the newest pending reply in the
          // top-ranked sub that still has pending.
          const lastPostBySub = new Map<string, number>();
          const acctActivity = activity[account.id];
          for (const post of acctActivity?.recent_posts ?? []) {
            if (!post.subreddit || !post.posted_at) continue;
            const s = post.subreddit.toLowerCase();
            const ms = parseServerUtc(post.posted_at);
            const cur = lastPostBySub.get(s);
            if (cur === undefined || ms > cur) lastPostBySub.set(s, ms);
          }

          // Group still-unused pending by sub (each list stays newest-first
          // because the source `pending` is sorted that way). Build two maps:
          // assigned (subs the account owns) and other (everything else).
          const assignedBySub = new Map<string, ReplyItem[]>();
          const otherBySub = new Map<string, ReplyItem[]>();
          for (const r of pending) {
            if (usedReplyIds.has(r.reply_id)) continue;
            const sub = (r.subreddit ?? "").toLowerCase();
            if (!sub) continue;
            const target = subFilter.includes(sub) ? assignedBySub : otherBySub;
            if (!target.has(sub)) target.set(sub, []);
            target.get(sub)!.push(r);
          }

          // Stable tiebreaker preferring subFilter order (then alphabetical
          // for non-assigned subs so the fallback is deterministic).
          const subOrderIndex = new Map(subFilter.map((s, i) => [s, i]));
          const subRankKey = (s: string) => subOrderIndex.get(s) ?? 1_000_000;
          const rankCandidateSubs = (m: Map<string, ReplyItem[]>): string[] =>
            [...m.keys()].sort((a, b) => {
              const av = lastPostBySub.get(a);
              const bv = lastPostBySub.get(b);
              if (av === undefined && bv === undefined) {
                const ai = subRankKey(a);
                const bi = subRankKey(b);
                if (ai !== bi) return ai - bi;
                return a.localeCompare(b);
              }
              if (av === undefined) return -1;
              if (bv === undefined) return 1;
              if (av !== bv) return av - bv;
              const ai = subRankKey(a);
              const bi = subRankKey(b);
              if (ai !== bi) return ai - bi;
              return a.localeCompare(b);
            });

          // Tier 1: pick the stalest-sub reply from the account's own subs.
          let chosen: ReplyItem | null = null;
          for (const sub of rankCandidateSubs(assignedBySub)) {
            const list = assignedBySub.get(sub);
            if (list && list.length) {
              chosen = list[0];
              break;
            }
          }

          // Tier 2 (swamp escape): if the chosen sub represents > threshold
          // of the account's available PENDING, also consider non-assigned
          // subs. The account's assigned subs are a *preference*, not a hard
          // constraint, so the operator isn't stuck on one sub when a
          // generation burst skewed the queue.
          //
          // Within Tier 2, sub-tier the candidates:
          //   Tier 2a — orphan subs (no enabled account owns them) first.
          //   Tier 2b — subs owned by another enabled account, as a last
          //   resort. Keeps brand isolation when at all possible.
          if (chosen) {
            const chosenSub = (chosen.subreddit ?? "").toLowerCase();
            const chosenSubCount = assignedBySub.get(chosenSub)?.length ?? 0;
            let assignedTotal = 0;
            for (const list of assignedBySub.values()) assignedTotal += list.length;
            const concentration =
              assignedTotal > 0 ? chosenSubCount / assignedTotal : 0;
            if (concentration > SWAMPED_THRESHOLD && otherBySub.size > 0) {
              const orphanBySub = new Map<string, ReplyItem[]>();
              const otherAcctBySub = new Map<string, ReplyItem[]>();
              for (const [sub, list] of otherBySub.entries()) {
                if (allAssignedSubs.has(sub)) {
                  otherAcctBySub.set(sub, list);
                } else {
                  orphanBySub.set(sub, list);
                }
              }
              let fallback: ReplyItem | null = null;
              for (const sub of rankCandidateSubs(orphanBySub)) {
                const list = orphanBySub.get(sub);
                if (list && list.length) {
                  fallback = list[0];
                  break;
                }
              }
              if (!fallback) {
                for (const sub of rankCandidateSubs(otherAcctBySub)) {
                  const list = otherAcctBySub.get(sub);
                  if (list && list.length) {
                    fallback = list[0];
                    break;
                  }
                }
              }
              if (fallback) chosen = fallback;
            }
          }

          if (chosen) {
            reply = chosen;
            usedReplyIds.add(chosen.reply_id);
          }
        }
      }
      const state = account
        ? deriveSlotState(account, activity[account.id], nowMs)
        : { kind: "disabled" as const };
      result.push({ slot, account, reply, state });
    }
    return result;
  }, [accounts, pending, activity, nowMs]);

  function withRefresh(action: () => Promise<unknown>, successMsg: string) {
    return runAction(async () => {
      await action();
      await Promise.all([loadPending(), loadAccountsHealth()]);
    }, successMsg);
  }

  return (
    <div className="space-y-5">
      <RepliesTabs />

      <Card className="p-3">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="font-semibold text-slate-800">Live posting board</span>
          <span className="text-muted">
            One reply per profile slot. Mark done after posting on Reddit to
            apply the per-account cooldown.
          </span>
          <Button
            size="sm"
            variant="secondary"
            disabled={busy || accounts.filter((a) => a.is_enabled).length === 0}
            title="Distribute tracked subreddits across enabled accounts, balanced by posts in the last 7 days."
            onClick={() =>
              runAction(async () => {
                await api.autoAssignSubreddits();
                await loadAccountsHealth();
              }, "Subreddits assigned across accounts")
            }
          >
            Auto-assign subreddits
          </Button>
          <Button
            size="sm"
            disabled={busy || accounts.filter((a) => a.is_enabled).length === 0}
            title="Run the LLM on already-scraped comments (no Apify) that don't have a reply yet, focusing on assigned subreddits with empty queues."
            onClick={() => {
              const enabled = accounts.filter((a) => a.is_enabled);
              const pendingByLowerSub = new Map<string, number>();
              for (const r of pending) {
                const k = (r.subreddit ?? "").toLowerCase();
                pendingByLowerSub.set(k, (pendingByLowerSub.get(k) ?? 0) + 1);
              }
              const targetSubs = new Set<string>();
              for (const a of enabled) {
                for (const sub of a.assigned_subreddits ?? []) {
                  if ((pendingByLowerSub.get(sub.toLowerCase()) ?? 0) < 5) {
                    targetSubs.add(sub);
                  }
                }
              }
              const list = [...targetSubs];
              if (!list.length) {
                runAction(async () => {}, "Every assigned subreddit already has 5+ pending replies");
                return;
              }
              runAction(async () => {
                const res = await api.generateRepliesFromExisting(list, 20);
                await loadPending();
                return res;
              }, `Queued ${list.length} generation jobs`);
            }}
          >
            Generate for empty slots
          </Button>
          <span className="ml-auto text-xs text-muted">
            {accounts.filter((a) => a.is_enabled).length} of {slots.length} slots filled · {pending.length} pending in queue
            {!hasLoadedOnce && !loadError && " · loading…"}
          </span>
        </div>
        {loadError && (
          <div className="mt-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800">
            <span className="font-semibold">Load error:</span> {loadError}
            <div className="mt-1 text-rose-700/80">
              Most likely the dashboard can't reach the API at <code>{process.env.NEXT_PUBLIC_API_BASE_URL || "(unset)"}</code> from your browser. Open DevTools → Network and check the failing request.
            </div>
          </div>
        )}
      </Card>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-3">
        {slots.map(({ slot, account, reply, state }) => (
          <SlotCard
            key={slot}
            slot={slot}
            account={account}
            reply={reply}
            state={state}
            busy={busy}
            edits={edits}
            setEdits={setEdits}
            postedUrls={postedUrls}
            setPostedUrls={setPostedUrls}
            onApprove={(r, text) =>
              withRefresh(
                () =>
                  api.updateReply(r.reply_id, {
                    status: "APPROVED",
                    reply_text: text,
                  }),
                "Draft approved for posting",
              )
            }
            onMarkDone={(r, accId, postedUrl, text) =>
              withRefresh(
                async () => {
                  await api.markReplyPostedByAccount(
                    r.reply_id,
                    accId,
                    postedUrl,
                    text,
                  );
                  setPostedUrls((prev) => {
                    const { [r.reply_id]: _drop, ...rest } = prev;
                    return rest;
                  });
                },
                `Marked posted by ${
                  accounts.find((a) => a.id === accId)?.username ?? "account"
                }`,
              )
            }
            onSave={(r, text) =>
              withRefresh(
                () => api.updateReply(r.reply_id, { reply_text: text }),
                "Draft saved",
              )
            }
            onDismiss={(r) => {
              if (!window.confirm(`Dismiss reply #${r.reply_id}?`)) return;
              withRefresh(
                () => api.updateReply(r.reply_id, { status: "DISMISSED" }),
                "Reply dismissed",
              );
            }}
            onSkip={(r) =>
              withRefresh(
                () => api.updateReply(r.reply_id, { status: "DISMISSED" }),
                "Skipped — pulling next from queue",
              )
            }
          />
        ))}
      </div>

      {!accounts.length && (
        <EmptyState
          title="No accounts yet"
          description="Add Reddit accounts in Settings / Accounts — each profile slot appears here once an account is assigned to it."
        />
      )}
    </div>
  );
}

function SlotCard({
  slot,
  account,
  reply,
  state,
  busy,
  edits,
  setEdits,
  postedUrls,
  setPostedUrls,
  onApprove,
  onMarkDone,
  onSave,
  onDismiss,
  onSkip,
}: {
  slot: number;
  account: RedditAccountItem | null;
  reply: ReplyItem | null;
  state: SlotState;
  busy: boolean;
  edits: Record<number, string>;
  setEdits: React.Dispatch<React.SetStateAction<Record<number, string>>>;
  postedUrls: Record<number, string>;
  setPostedUrls: React.Dispatch<React.SetStateAction<Record<number, string>>>;
  onApprove: (reply: ReplyItem, text: string) => void;
  onMarkDone: (
    reply: ReplyItem,
    accountId: number,
    postedUrl: string,
    text: string,
  ) => void;
  onSave: (reply: ReplyItem, text: string) => void;
  onDismiss: (reply: ReplyItem) => void;
  onSkip: (reply: ReplyItem) => void;
}) {
  const editingText =
    reply && edits[reply.reply_id] !== undefined
      ? edits[reply.reply_id]
      : reply?.reply_text ?? "";
  const postedUrlInput = reply ? postedUrls[reply.reply_id] ?? "" : "";
  const trimmedPostedUrl = postedUrlInput.trim();
  const hasPostedUrlInput = trimmedPostedUrl.length > 0;
  const isPostedUrlValid =
    hasPostedUrlInput && isValidRedditCommentUrl(trimmedPostedUrl);
  const isLocked = state.kind !== "active";
  const changed = reply ? editingText !== reply.reply_text : false;
  const slotLabel = `Slot ${slot}`;

  if (!account) {
    return (
      <div className="overflow-hidden rounded-xl border border-dashed border-slate-200 bg-slate-50/40 p-5">
        <div className="flex items-center gap-2 text-xs">
          <span className="rounded bg-white px-1.5 py-0.5 font-mono text-[11px] text-slate-500 ring-1 ring-slate-200">
            {slotLabel}
          </span>
          <span className="text-muted">No account assigned</span>
        </div>
        <div className="mt-6 text-center text-xs text-muted">
          Assign an account with profile slot {slot} in Settings / Accounts.
        </div>
      </div>
    );
  }

  const dimClass = isLocked ? "opacity-60" : "";

  // Big centered countdown shown while the slot is locked. Pulls a label
  // from the slot state so cooldown / hourly / daily all share the same
  // visual treatment.
  const overlayInfo = (() => {
    if (state.kind === "cooldown")
      return { label: "Cooldown", seconds: state.secondsLeft, tone: "amber" as const };
    if (state.kind === "hourly")
      return {
        label: `Hourly cap ${state.used}/${state.cap}`,
        seconds: state.resetsInSeconds,
        tone: "rose" as const,
      };
    if (state.kind === "daily")
      return {
        label: `Daily cap ${state.used}/${state.cap}`,
        seconds: state.resetsInSeconds,
        tone: "rose" as const,
      };
    return null;
  })();

  return (
    <div
      className={`group relative overflow-hidden rounded-xl border bg-white transition-all ${
        isLocked ? "border-slate-200" : "border-border hover:shadow-sm"
      }`}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-slate-100 bg-slate-50/40 px-3 py-2 text-xs">
        <span
          className="rounded bg-white px-1.5 py-0.5 font-mono text-[11px] text-slate-600 ring-1 ring-slate-200"
          title={account.profile_summary ?? ""}
        >
          {slotLabel}
        </span>
        <span className="font-semibold text-slate-800">u/{account.username}</span>
        <AssignedSubsBadge subs={account.assigned_subreddits ?? []} />
        {!account.is_enabled && (
          <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-500">
            disabled
          </span>
        )}
        {state.kind === "cooldown" && (
          <span className="inline-flex items-center rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-700 ring-1 ring-amber-200">
            cooldown
          </span>
        )}
        {state.kind === "hourly" && (
          <span className="inline-flex items-center rounded-full bg-rose-50 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-rose-700 ring-1 ring-rose-200">
            hourly cap
          </span>
        )}
        {state.kind === "daily" && (
          <span className="inline-flex items-center rounded-full bg-rose-50 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-rose-700 ring-1 ring-rose-200">
            daily cap
          </span>
        )}
        {reply && (
          <>
            <span className="text-slate-300">·</span>
            <span className="font-medium text-slate-700">
              {reply.platform === "glp"
                ? `glp/${reply.platform_section ?? "forum"}`
                : reply.platform === "chan"
                ? `/${reply.platform_section ?? reply.subreddit ?? "board"}/`
                : `r/${reply.subreddit}`}
            </span>
            <span
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${
                reply.includes_promo
                  ? "bg-amber-50 text-amber-700 ring-1 ring-amber-200"
                  : "bg-teal-50 text-teal-700 ring-1 ring-teal-200"
              }`}
            >
              {reply.includes_promo ? "promo" : "normal"}
            </span>
            <span className="ml-auto font-mono text-[11px] text-slate-400">
              #{reply.reply_id}
            </span>
            <button
              type="button"
              aria-label={`Skip reply #${reply.reply_id} and pull next from queue`}
              title="Skip — pull the next reply from the queue"
              disabled={busy}
              onClick={() => onSkip(reply)}
              className="ml-1 inline-flex h-5 w-5 items-center justify-center rounded-full text-slate-400 transition hover:bg-rose-50 hover:text-rose-600 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="h-3 w-3"
                aria-hidden="true"
              >
                <line x1="6" y1="6" x2="18" y2="18" />
                <line x1="18" y1="6" x2="6" y2="18" />
              </svg>
            </button>
          </>
        )}
        {!reply && state.kind === "active" && (
          <span className="ml-auto text-muted">queue empty</span>
        )}
      </div>

      {/* Status banner */}
      {state.kind === "cooldown" && (
        <div className="flex items-center justify-between border-b border-amber-100 bg-amber-50/60 px-3 py-1.5 text-xs text-amber-800">
          <span>Ready in</span>
          <span className="font-mono font-semibold">
            {formatCountdown(state.secondsLeft)}
          </span>
        </div>
      )}
      {state.kind === "hourly" && (
        <div className="flex items-center justify-between border-b border-rose-100 bg-rose-50/60 px-3 py-1.5 text-xs text-rose-800">
          <span>
            Hourly cap {state.used}/{state.cap} reached
          </span>
          <span className="font-mono font-semibold">
            resets in {formatCountdown(state.resetsInSeconds)}
          </span>
        </div>
      )}
      {state.kind === "daily" && (
        <div className="flex items-center justify-between border-b border-rose-100 bg-rose-50/60 px-3 py-1.5 text-xs text-rose-800">
          <span>
            Daily cap {state.used}/{state.cap} reached
          </span>
          <span className="font-mono font-semibold">
            resets in {formatCountdown(state.resetsInSeconds)}
          </span>
        </div>
      )}
      {state.kind === "disabled" && (
        <div className="border-b border-slate-100 bg-slate-50 px-3 py-1.5 text-xs text-slate-500">
          Account disabled — re-enable in Settings / Accounts to use this slot.
        </div>
      )}

      {/* Body */}
      {reply ? (
        <div className={`grid gap-3 p-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] ${dimClass}`}>
          <div className="min-w-0 space-y-2">
            <h3
              className="line-clamp-2 text-sm font-semibold text-slate-900"
              title={reply.post_title}
            >
              {reply.post_title}
            </h3>
            <blockquote className="line-clamp-4 border-l-2 border-slate-300 pl-3 text-xs leading-relaxed text-slate-700">
              {reply.comment_text}
            </blockquote>
            <div className="flex flex-wrap items-center gap-3 text-[11px]">
              {reply.comment_url && (
                <a
                  href={reply.comment_url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-slate-600 hover:text-slate-900 hover:underline"
                >
                  Open on reddit ↗
                </a>
              )}
              {reply.comment_author && (
                <span className="text-muted">u/{reply.comment_author}</span>
              )}
              <span className="text-muted">↑{reply.comment_upvotes} cmt</span>
              <span className="text-muted">↑{reply.post_upvotes} post</span>
            </div>
          </div>

          <div className="min-w-0 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-muted">
                Draft reply
              </span>
              {changed && (
                <span className="text-[10px] font-medium text-amber-700">Unsaved</span>
              )}
            </div>
            <Textarea
              value={editingText}
              readOnly={isLocked}
              onChange={(event) =>
                setEdits((prev) => ({
                  ...prev,
                  [reply.reply_id]: event.target.value,
                }))
              }
              className="min-h-[100px] text-sm"
            />
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <label
                  htmlFor={`posted-url-${reply.reply_id}`}
                  className="text-[10px] font-semibold uppercase tracking-wide text-muted"
                >
                  Posted reply URL
                </label>
                {hasPostedUrlInput && !isPostedUrlValid && (
                  <span className="text-[10px] font-medium text-rose-700">
                    Not a Reddit comment link
                  </span>
                )}
                {isPostedUrlValid && (
                  <span className="text-[10px] font-medium text-emerald-700">
                    Looks good
                  </span>
                )}
              </div>
              <Input
                id={`posted-url-${reply.reply_id}`}
                type="url"
                inputMode="url"
                placeholder="https://www.reddit.com/r/.../comments/..."
                value={postedUrlInput}
                readOnly={isLocked}
                onChange={(event) =>
                  setPostedUrls((prev) => ({
                    ...prev,
                    [reply.reply_id]: event.target.value,
                  }))
                }
                className={`h-9 text-xs ${
                  hasPostedUrlInput && !isPostedUrlValid
                    ? "border-rose-300 focus:border-rose-500 focus:ring-rose-200"
                    : ""
                }`}
              />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                onClick={() =>
                  onMarkDone(reply, account.id, trimmedPostedUrl, editingText)
                }
                disabled={
                  busy ||
                  isLocked ||
                  !editingText.trim() ||
                  !isPostedUrlValid
                }
                title={
                  isLocked
                    ? "Slot is in cooldown or at limit"
                    : !isPostedUrlValid
                    ? "Paste the Reddit comment URL above to enable"
                    : "Record this as posted by this account and start cooldown"
                }
              >
                Mark done
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => onApprove(reply, editingText)}
                disabled={busy || isLocked || !editingText.trim()}
                title="Approve for the worker to post"
              >
                Approve
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => onSave(reply, editingText)}
                disabled={busy || !editingText.trim() || !changed}
                title="Save edits without changing status"
              >
                Save
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="ml-auto text-rose-600 hover:bg-rose-50"
                onClick={() => onDismiss(reply)}
                disabled={busy || isLocked}
              >
                Dismiss
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <div className="p-6 text-center text-xs text-muted">
          {state.kind === "active"
            ? "No pending reply for this slot — generate more or scrape new content."
            : "Slot will pick the next pending reply when it becomes available."}
        </div>
      )}

      {overlayInfo && (
        <div
          className={`pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-1 backdrop-blur-[2px] ${
            overlayInfo.tone === "amber"
              ? "bg-amber-50/85"
              : "bg-rose-50/85"
          }`}
          aria-live="polite"
        >
          <div
            className={`text-[11px] font-semibold uppercase tracking-wider ${
              overlayInfo.tone === "amber" ? "text-amber-700" : "text-rose-700"
            }`}
          >
            {overlayInfo.label}
          </div>
          <div
            className={`font-mono text-4xl font-bold tabular-nums ${
              overlayInfo.tone === "amber" ? "text-amber-900" : "text-rose-900"
            }`}
          >
            {formatCountdown(overlayInfo.seconds)}
          </div>
          <div
            className={`text-[10px] ${
              overlayInfo.tone === "amber" ? "text-amber-700/80" : "text-rose-700/80"
            }`}
          >
            {state.kind === "cooldown" ? "next post unlocks at 0:00" : "resets in"}
          </div>
        </div>
      )}
    </div>
  );
}
