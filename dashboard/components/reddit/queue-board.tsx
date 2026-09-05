"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Check, ExternalLink, SkipForward, X } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  type AccountActivity,
  type BrandConfig,
  type RedditAccountItem,
  type RedditAutomationSummary,
  type ReplyItem,
} from "@/lib/api";
import { useAccountsHealth } from "@/lib/hooks/use-accounts-health";
import { usePendingReplies, useUpdateReply } from "@/lib/hooks/use-replies";
import { queryKeys } from "@/lib/query-keys";
import { cn } from "@/lib/utils";

const MIN_SLOT_COUNT = 10;
// When one sub accounts for >SWAMPED_THRESHOLD of an account's unused PENDING
// pool, the slot picker also considers replies from subs OUTSIDE the account's
// assigned_subreddits — so the operator isn't stuck cycling through a single
// dominant sub when a generation burst skewed the queue.
const SWAMPED_THRESHOLD = 0.5;
const HOLD_REASON_LABELS: Record<string, string> = {
  blocked_risky_keyword: "Held: sensitive topic",
  blocked_promo_fit: "Held: promo didn't fit",
  blocked_normal_daily_cap: "Held: daily cap",
  blocked_promo_daily_cap: "Held: promo cap",
  blocked_subreddit_cap: "Held: per-sub cap",
};

function holdReasonLabel(reply: ReplyItem): string {
  if (reply.auto_approval_reason && HOLD_REASON_LABELS[reply.auto_approval_reason]) {
    return HOLD_REASON_LABELS[reply.auto_approval_reason];
  }
  if (reply.auto_approval_reason) return `Held: ${reply.auto_approval_reason}`;
  return "Needs review";
}

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
  | { kind: "disabled" }
  | { kind: "banned"; detail: string | null; sessionAlive: boolean | null }
  | { kind: "session_dead"; detail: string | null }
  | { kind: "no_cookies" }
  | { kind: "proxy_dead"; detail: string | null };

function AssignedSubsBadge({ subs }: { subs: string[] }) {
  if (!subs.length) {
    return (
      <Badge
        variant="outline"
        className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground"
        title="No subreddits assigned — this slot pulls from the full pending pool. Click 'Auto-assign subreddits' to balance the workload."
      >
        any sub
      </Badge>
    );
  }
  const preview = subs.slice(0, 2).join(", ");
  const more = subs.length > 2 ? ` +${subs.length - 2}` : "";
  return (
    <Badge
      variant="secondary"
      className="max-w-[260px] truncate text-[10px] font-medium"
      title={subs.join(", ")}
    >
      {preview}
      {more}
    </Badge>
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
  if (account.status === "BANNED" || account.reddit_health === "BANNED") {
    return {
      kind: "banned",
      detail: account.reddit_health_detail ?? null,
      sessionAlive: account.reddit_session_alive ?? null,
    };
  }
  if (!account.is_enabled) return { kind: "disabled" };
  if (account.reddit_health === "SESSION_DEAD") {
    return { kind: "session_dead", detail: account.reddit_health_detail ?? null };
  }
  if (account.reddit_health === "NO_COOKIES") {
    return { kind: "no_cookies" };
  }
  if (account.reddit_health === "PROXY_DEAD") {
    return { kind: "proxy_dead", detail: account.reddit_health_detail ?? null };
  }
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

function LoadingGrid() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-16 rounded-xl" />
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} className="h-64 rounded-xl" />
        ))}
      </div>
    </div>
  );
}

function ErrorBanner({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <Alert variant="destructive">
      <AlertCircle className="h-4 w-4" />
      <AlertTitle>Load error</AlertTitle>
      <AlertDescription className="space-y-2">
        <p>{message}</p>
        <p className="text-destructive/80">
          Most likely the dashboard can&apos;t reach the API at{" "}
          <code>{process.env.NEXT_PUBLIC_API_BASE_URL || "(unset)"}</code> from
          your browser. Open DevTools → Network and check the failing request.
        </p>
        <Button type="button" size="sm" variant="outline" onClick={onRetry}>
          Retry
        </Button>
      </AlertDescription>
    </Alert>
  );
}

export function QueueBoard() {
  const queryClient = useQueryClient();
  const updateReply = useUpdateReply();
  const [brandFilter, setBrandFilter] = useState("all");
  const brandId =
    brandFilter !== "all" && Number.isFinite(Number(brandFilter))
      ? Number(brandFilter)
      : undefined;

  const healthQuery = useAccountsHealth(true);
  const pendingQuery = usePendingReplies(brandId);
  const brandsQuery = useQuery({
    queryKey: queryKeys.brands(),
    queryFn: () => api.brands().catch(() => [] as BrandConfig[]),
    placeholderData: (previous) => previous,
  });
  const automationQuery = useQuery({
    queryKey: queryKeys.redditAutomation({ limit: 5 }),
    queryFn: () => api.redditAutomation({ limit: 5 }),
    refetchInterval: 15_000,
    placeholderData: (previous) => previous,
  });
  const queueQuery = useQuery({
    queryKey: queryKeys.workerQueue("reddit"),
    queryFn: async () => {
      try {
        return await api.workerQueue("reddit");
      } catch {
        return { counts: {} as Record<string, number> };
      }
    },
    refetchInterval: 15_000,
    placeholderData: (previous) => previous,
  });

  const accounts = healthQuery.data?.accounts ?? [];
  const activity = healthQuery.data?.activity ?? {};
  const pending = pendingQuery.data ?? [];
  const brands = brandsQuery.data ?? [];
  const automationSummary = automationQuery.data ?? null;
  const queueCounts = queueQuery.data?.counts ?? {};

  const [nowMs, setNowMs] = useState(() => Date.now());
  const [edits, setEdits] = useState<Record<number, string>>({});
  const [postedUrls, setPostedUrls] = useState<Record<number, string>>({});
  const [actionBusy, setActionBusy] = useState(false);
  const busy = actionBusy || updateReply.isPending;
  const hasLoadedOnce = healthQuery.isFetched && pendingQuery.isFetched;
  const loadError =
    (healthQuery.error instanceof Error && healthQuery.error.message) ||
    (pendingQuery.error instanceof Error && pendingQuery.error.message) ||
    null;

  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const invalidateBoard = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["replies"] });
    void queryClient.invalidateQueries({ queryKey: queryKeys.accountsHealth(true) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.workerQueue("reddit") });
    void queryClient.invalidateQueries({
      queryKey: queryKeys.redditAutomation({ limit: 5 }),
    });
  }, [queryClient]);

  const runApi = useCallback(
    async (action: () => Promise<unknown>, successMsg: string) => {
      setActionBusy(true);
      try {
        await action();
        toast.success(successMsg);
        invalidateBoard();
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Action failed");
      } finally {
        setActionBusy(false);
      }
    },
    [invalidateBoard],
  );

  // Build slot assignments: for each profile_index, show every enabled account
  // at that slot. Older data can have duplicate profile slots, and collapsing
  // to one account hides real automation accounts from the queue page.
  const slots = useMemo(() => {
    const redditAccounts = accounts.filter(
      (account) => (account.platform || "reddit") === "reddit",
    );
    const slotCount = Math.max(
      MIN_SLOT_COUNT,
      ...redditAccounts.map((a) => (a.profile_index ?? 0) + 1),
    );
    const statusRank = (acc: RedditAccountItem) => {
      if (acc.reddit_health === "BANNED" || acc.status === "BANNED") return -1;
      switch (acc.status) {
        case "ACTIVE":
          return 0;
        case "VERIFYING":
          return 1;
        case "NEW":
          return 2;
        case "NEEDS_REAUTH":
          return 3;
        case "FAILED":
          return 4;
        case "DISABLED":
          return 5;
        default:
          return 6;
      }
    };
    const accountsBySlot = new Map<number, RedditAccountItem[]>();
    const sorted = [...redditAccounts].sort((a, b) => {
      const aBanned = a.status === "BANNED" || a.reddit_health === "BANNED";
      const bBanned = b.status === "BANNED" || b.reddit_health === "BANNED";
      if (aBanned !== bBanned) return aBanned ? -1 : 1;
      if (a.is_enabled !== b.is_enabled) return a.is_enabled ? -1 : 1;
      const rank = statusRank(a) - statusRank(b);
      if (rank !== 0) return rank;
      return a.id - b.id;
    });
    for (const acc of sorted) {
      const slot = Math.max(0, Math.min(slotCount - 1, acc.profile_index ?? 0));
      if (!accountsBySlot.has(slot)) accountsBySlot.set(slot, []);
      accountsBySlot.get(slot)!.push(acc);
    }
    const defaultBrandId = brands.find((brand) => brand.is_active)?.id ?? null;
    const replyMatchesAccount = (reply: ReplyItem, account: RedditAccountItem) => {
      const replyBrand = reply.brand_id ?? defaultBrandId;
      const accountBrand = account.brand_id ?? defaultBrandId;
      return replyBrand === accountBrand;
    };
    // Union of subs owned by ANY enabled account. Used inside Tier 2 (swamp
    // escape) to prefer truly orphan subs over subs that belong to other
    // active accounts - keeps brand isolation as strong as possible while
    // still letting a swamped account pick from outside its own filter.
    const allAssignedSubs = new Set<string>();
    for (const acc of redditAccounts) {
      if (!acc.is_enabled) continue;
      for (const s of acc.assigned_subreddits ?? []) {
        const lower = s.toLowerCase();
        if (lower) allAssignedSubs.add(lower);
      }
    }
    const usedReplyIds = new Set<number>();
    const result: {
      slot: number;
      slotPosition: number;
      slotTotal: number;
      account: RedditAccountItem | null;
      reply: ReplyItem | null;
      state: SlotState;
    }[] = [];
    const appendSlotCard = (
      slot: number,
      account: RedditAccountItem | null,
      slotPosition: number,
      slotTotal: number,
    ) => {
      let reply: ReplyItem | null = null;
      if (account && account.is_enabled) {
        const subFilter = (account.assigned_subreddits ?? [])
          .map((s) => s.toLowerCase())
          .filter(Boolean);
        if (subFilter.length === 0) {
          // No sub filter: newest unused draft for this account's brand.
          const next = pending.find(
            (r) => !usedReplyIds.has(r.reply_id) && replyMatchesAccount(r, account),
          );
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
            if (!replyMatchesAccount(r, account)) continue;
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
          //   Tier 2a - orphan subs (no enabled account owns them) first.
          //   Tier 2b - subs owned by another enabled account, as a last
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
      result.push({ slot, slotPosition, slotTotal, account, reply, state });
    };
    for (let slot = 0; slot < slotCount; slot++) {
      const slotAccounts = accountsBySlot.get(slot) ?? [];
      const enabledAccounts = slotAccounts.filter((account) => account.is_enabled);
      const bannedAccounts = slotAccounts.filter(
        (account) => account.status === "BANNED" || account.reddit_health === "BANNED",
      );
      const visibleAccounts =
        enabledAccounts.length > 0 || bannedAccounts.length > 0
          ? [
              ...bannedAccounts,
              ...enabledAccounts.filter((account) => !bannedAccounts.includes(account)),
            ]
          : slotAccounts.slice(0, 1);
      if (!visibleAccounts.length) {
        appendSlotCard(slot, null, 0, 0);
        continue;
      }
      visibleAccounts.forEach((account, index) =>
        appendSlotCard(slot, account, index, visibleAccounts.length),
      );
    }
    return result;
  }, [accounts, pending, activity, nowMs, brands]);

  if (healthQuery.isPending && !healthQuery.data) {
    return <LoadingGrid />;
  }

  if (healthQuery.isError && !healthQuery.data) {
    return (
      <ErrorBanner
        message={loadError || "Failed to load"}
        onRetry={() => {
          void healthQuery.refetch();
          void pendingQuery.refetch();
        }}
      />
    );
  }

  return (
    <div className="space-y-4">
      {loadError ? (
        <ErrorBanner
          message={loadError}
          onRetry={() => {
            void healthQuery.refetch();
            void pendingQuery.refetch();
          }}
        />
      ) : null}

      {automationSummary && <QueueAutomationStatus summary={automationSummary} />}

      <Card className="p-3 shadow-none">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="font-semibold text-foreground">Reddit review board</span>
          <span className="text-muted-foreground">
            Edit and dismiss here. Approve queues the draft for the poster.
            Mark done after you post it yourself.
          </span>
          <Badge variant="secondary">
            {queueCounts.PENDING ?? pending.length} pending
          </Badge>
          <Badge variant="outline" className="border-emerald-500/30 text-emerald-600 dark:text-emerald-400">
            {queueCounts.APPROVED ?? 0} approved
          </Badge>
          <Badge variant="outline">
            {pending.filter((item) => !item.brand_id).length} untagged
          </Badge>
          <Select
            value={brandFilter}
            onValueChange={setBrandFilter}
          >
            <SelectTrigger
              className="h-8 w-44"
              title="Filter the pending queue by brand"
            >
              <SelectValue placeholder="All brands" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All brands</SelectItem>
              {brands.map((brand) => (
                <SelectItem
                  key={brand.id ?? brand.name}
                  value={String(brand.id ?? brand.name)}
                >
                  {brand.name}
                  {brand.is_active ? " (default)" : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={busy}
            title="Scrape every tracked subreddit now"
            onClick={() =>
              void runApi(async () => {
                await api.scrapeAll(15);
              }, "Scrape queued for tracked subs")
            }
          >
            Scrape now
          </Button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={busy || pending.filter((item) => !item.brand_id).length === 0}
            title="Stamp missing brand_id from the subreddit owner"
            onClick={() =>
              void runApi(
                () => api.stampReplyBrands(),
                "Tagged untagged drafts with their brand",
              )
            }
          >
            Stamp brands
          </Button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={busy || accounts.filter((a) => a.is_enabled).length === 0}
            title="Distribute tracked subreddits across enabled accounts, balanced by posts in the last 7 days."
            onClick={() =>
              void runApi(async () => {
                await api.autoAssignSubreddits();
              }, "Subreddits assigned across accounts")
            }
          >
            Auto-assign subreddits
          </Button>
          <Button
            type="button"
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
                toast.success("Every assigned subreddit already has 5+ pending replies");
                return;
              }
              void runApi(async () => {
                await api.generateRepliesFromExisting(list, 20);
              }, `Queued ${list.length} generation jobs`);
            }}
          >
            Generate for empty slots
          </Button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={busy || !slots.some((slot) => slot.reply)}
            title="Approve every draft currently shown on a slot so the poster can claim it"
            onClick={() => {
              const ids = slots
                .map((slot) => slot.reply?.reply_id)
                .filter((id): id is number => typeof id === "number");
              if (!ids.length) return;
              if (!window.confirm(`Approve ${ids.length} visible drafts for posting?`)) return;
              void runApi(
                () => api.bulkUpdateReplies(ids, "APPROVED"),
                `Approved ${ids.length} drafts`,
              );
            }}
          >
            Approve visible
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="text-destructive hover:text-destructive"
            disabled={busy || !slots.some((slot) => slot.reply)}
            title="Dismiss every draft currently shown on a slot"
            onClick={() => {
              const ids = slots
                .map((slot) => slot.reply?.reply_id)
                .filter((id): id is number => typeof id === "number");
              if (!ids.length) return;
              if (!window.confirm(`Dismiss ${ids.length} visible drafts?`)) return;
              void runApi(
                () => api.bulkUpdateReplies(ids, "DISMISSED"),
                `Dismissed ${ids.length} drafts`,
              );
            }}
          >
            Dismiss visible
          </Button>
          <span className="ml-auto text-xs text-muted-foreground">
            {slots.filter((slot) => slot.account).length} account cards · {pending.length} pending in queue
            {!hasLoadedOnce && !loadError && " · loading…"}
          </span>
        </div>
      </Card>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-3">
        {slots.map(({ slot, slotPosition, slotTotal, account, reply, state }) => (
          <SlotCard
            key={account ? `${slot}-${account.id}` : `empty-${slot}`}
            slot={slot}
            slotPosition={slotPosition}
            slotTotal={slotTotal}
            account={account}
            reply={reply}
            state={state}
            busy={busy}
            edits={edits}
            setEdits={setEdits}
            postedUrls={postedUrls}
            setPostedUrls={setPostedUrls}
            onApprove={(r, text) =>
              updateReply.mutate({
                id: r.reply_id,
                status: "APPROVED",
                reply_text: text,
              })
            }
            onMarkDone={(r, accId, postedUrl, text) =>
              void runApi(
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
              updateReply.mutate({
                id: r.reply_id,
                reply_text: text,
              })
            }
            onDismiss={(r) => {
              if (!window.confirm(`Dismiss reply #${r.reply_id}?`)) return;
              updateReply.mutate({
                id: r.reply_id,
                status: "DISMISSED",
              });
            }}
            onSkip={(r) =>
              updateReply.mutate({
                id: r.reply_id,
                status: "DISMISSED",
              })
            }
            brandName={
              reply?.brand_id
                ? brands.find((brand) => brand.id === reply.brand_id)?.name ?? "tagged"
                : reply
                  ? "untagged"
                  : null
            }
          />
        ))}
      </div>

      {!accounts.length && (
        <Card className="p-8 text-center shadow-none">
          <p className="text-sm font-medium">No accounts yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Add Reddit accounts in Settings / Accounts - each profile slot appears here once an account is assigned to it.
          </p>
          <Button asChild className="mt-4">
            <Link href="/settings?tab=accounts">Go to accounts</Link>
          </Button>
        </Card>
      )}
    </div>
  );
}

function QueueAutomationStatus({ summary }: { summary: RedditAutomationSummary }) {
  const state = summary.current_state;
  const toneClass =
    state.state === "ready" || state.state === "posting"
      ? "border-emerald-500/30 bg-emerald-500/10"
      : state.state === "cooldown" || state.state === "idle_empty_queue"
        ? "border-amber-500/30 bg-amber-500/10"
        : "border-destructive/30 bg-destructive/10";
  const readyAccounts = summary.accounts.filter((account) => account.readiness_status === "ready").length;

  return (
    <Card className={cn("p-4 shadow-none", toneClass)}>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Badge variant="outline" className="bg-background/80 font-semibold">
              {state.worker_running ? "Worker active" : "Worker not confirmed"}
            </Badge>
            <Badge variant="outline" className="bg-background/80 font-semibold">
              {state.title}
            </Badge>
          </div>
          <div className="mt-2 font-semibold text-foreground">{state.detail}</div>
          {state.blockers.length > 0 && (
            <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
              {state.blockers.slice(0, 3).map((blocker) => (
                <li key={blocker} className="break-words">{blocker}</li>
              ))}
            </ul>
          )}
        </div>
        <div className="grid shrink-0 gap-2 text-sm sm:grid-cols-3 lg:min-w-[520px]">
          <QueueStatusFact label="Approved" value={String(state.approved_queue_count)} />
          <QueueStatusFact label="Ready accounts" value={`${readyAccounts} / ${summary.account_count}`} />
          <QueueStatusFact label="Active account" value={state.active_account_username ? `u/${state.active_account_username}` : "None"} />
        </div>
      </div>
    </Card>
  );
}

function QueueStatusFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border/80 bg-background/60 p-3">
      <div className="text-xs font-semibold uppercase text-muted-foreground">{label}</div>
      <div className="mt-1 truncate font-medium text-foreground">{value}</div>
    </div>
  );
}

function SlotCard({
  slot,
  slotPosition,
  slotTotal,
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
  brandName,
}: {
  slot: number;
  slotPosition: number;
  slotTotal: number;
  account: RedditAccountItem | null;
  reply: ReplyItem | null;
  state: SlotState;
  busy: boolean;
  edits: Record<number, string>;
  setEdits: Dispatch<SetStateAction<Record<number, string>>>;
  postedUrls: Record<number, string>;
  setPostedUrls: Dispatch<SetStateAction<Record<number, string>>>;
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
  brandName: string | null;
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
  const duplicateLabel =
    account && slotTotal > 1 ? `duplicate ${slotPosition + 1}/${slotTotal}` : null;

  if (!account) {
    return (
      <Card className="overflow-hidden border-dashed p-5 shadow-none">
        <div className="flex items-center gap-2 text-xs">
          <Badge variant="outline" className="font-mono text-[11px]">
            {slotLabel}
          </Badge>
          {duplicateLabel && (
            <Badge variant="secondary" className="text-[11px] font-semibold text-amber-700 dark:text-amber-400">
              {duplicateLabel}
            </Badge>
          )}
          <span className="text-muted-foreground">No account assigned</span>
        </div>
        <div className="mt-6 text-center text-xs text-muted-foreground">
          Assign an account with profile slot {slot} in Settings / Accounts.
        </div>
      </Card>
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
    <Card
      className={cn(
        "group relative overflow-hidden shadow-none transition-all",
        isLocked ? "border-border" : "hover:border-primary/40",
      )}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b bg-muted/40 px-3 py-2 text-xs">
        <Badge
          variant="outline"
          className="font-mono text-[11px]"
          title={account.profile_summary ?? ""}
        >
          {slotLabel}
        </Badge>
        <span className="font-mono font-semibold text-foreground">u/{account.username}</span>
        {duplicateLabel && (
          <Badge variant="secondary" className="text-[11px] font-semibold text-amber-700 dark:text-amber-400">
            {duplicateLabel}
          </Badge>
        )}
        <AssignedSubsBadge subs={account.assigned_subreddits ?? []} />
        {(account.status === "BANNED" || account.reddit_health === "BANNED") && (
          <Badge variant="destructive" className="text-[10px] uppercase tracking-wide">
            banned
          </Badge>
        )}
        {account.reddit_health === "SESSION_DEAD" && (
          <Badge variant="secondary" className="text-[10px] uppercase tracking-wide text-amber-700 dark:text-amber-400">
            session dead
          </Badge>
        )}
        {account.reddit_health === "NO_COOKIES" && (
          <Badge variant="secondary" className="text-[10px] uppercase tracking-wide text-amber-700 dark:text-amber-400">
            no cookies
          </Badge>
        )}
        {!account.is_enabled && account.reddit_health !== "BANNED" && account.status !== "BANNED" && (
          <Badge variant="outline" className="text-[10px] uppercase tracking-wide text-muted-foreground">
            disabled
          </Badge>
        )}
        {state.kind === "cooldown" && (
          <Badge variant="secondary" className="text-[10px] uppercase tracking-wide text-amber-700 dark:text-amber-400">
            cooldown
          </Badge>
        )}
        {state.kind === "hourly" && (
          <Badge variant="destructive" className="text-[10px] uppercase tracking-wide">
            hourly cap
          </Badge>
        )}
        {state.kind === "daily" && (
          <Badge variant="destructive" className="text-[10px] uppercase tracking-wide">
            daily cap
          </Badge>
        )}
        {reply && (
          <>
            <span className="text-muted-foreground">·</span>
            <span className="font-medium text-foreground">
              {reply.platform === "glp"
                ? `glp/${reply.platform_section ?? "forum"}`
                : reply.platform === "chan"
                ? `/${reply.platform_section ?? reply.subreddit ?? "board"}/`
                : `r/${reply.subreddit}`}
            </span>
            <Badge
              variant="outline"
              className={cn(
                "text-[10px] font-medium",
                reply.includes_promo
                  ? "border-amber-500/30 text-amber-700 dark:text-amber-400"
                  : "border-primary/30 text-primary",
              )}
            >
              {reply.includes_promo ? "promo" : "normal"}
            </Badge>
            {brandName && (
              <Badge
                variant="outline"
                className={cn(
                  "text-[10px] font-medium",
                  brandName === "untagged"
                    ? "border-destructive/30 text-destructive"
                    : "border-primary/30 text-foreground",
                )}
              >
                {brandName}
              </Badge>
            )}
            <Badge variant="secondary" className="text-[10px] font-medium">
              {holdReasonLabel(reply)}
            </Badge>
            <span className="ml-auto font-mono text-[11px] text-muted-foreground">
              #{reply.reply_id}
            </span>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Skip reply #${reply.reply_id} and pull next from queue`}
              title="Skip — pull the next reply from the queue"
              disabled={busy}
              onClick={() => onSkip(reply)}
              className="ml-1 h-5 w-5 text-muted-foreground hover:text-destructive"
            >
              <SkipForward />
            </Button>
          </>
        )}
        {!reply && state.kind === "active" && (
          <span className="ml-auto text-muted-foreground">queue empty</span>
        )}
      </div>

      {state.kind === "cooldown" && (
        <div className="flex items-center justify-between border-b border-amber-500/20 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-800 dark:text-amber-400">
          <span>Ready in</span>
          <span className="font-mono font-semibold">
            {formatCountdown(state.secondsLeft)}
          </span>
        </div>
      )}
      {state.kind === "hourly" && (
        <div className="flex items-center justify-between border-b border-destructive/20 bg-destructive/10 px-3 py-1.5 text-xs text-destructive">
          <span>
            Hourly cap {state.used}/{state.cap} reached
          </span>
          <span className="font-mono font-semibold">
            resets in {formatCountdown(state.resetsInSeconds)}
          </span>
        </div>
      )}
      {state.kind === "daily" && (
        <div className="flex items-center justify-between border-b border-destructive/20 bg-destructive/10 px-3 py-1.5 text-xs text-destructive">
          <span>
            Daily cap {state.used}/{state.cap} reached
          </span>
          <span className="font-mono font-semibold">
            resets in {formatCountdown(state.resetsInSeconds)}
          </span>
        </div>
      )}
      {state.kind === "banned" && (
        <div className="border-b border-destructive/30 bg-destructive/10 px-3 py-1.5 text-xs text-destructive">
          Banned on Reddit
          {state.sessionAlive
            ? " — session still logged in, but the public profile is banned. Cannot post."
            : " — public profile is the source of truth."}
          {state.detail ? ` ${state.detail}` : ""}
        </div>
      )}
      {state.kind === "session_dead" && (
        <div className="border-b border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-800 dark:text-amber-400">
          Session dead — cookies are not authenticated. {state.detail ?? "Paste fresh cookies."}
        </div>
      )}
      {state.kind === "no_cookies" && (
        <div className="border-b border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-800 dark:text-amber-400">
          No session cookies stored. Paste cookies before this slot can post.
        </div>
      )}
      {state.kind === "proxy_dead" && (
        <div className="border-b border-destructive/30 bg-destructive/10 px-3 py-1.5 text-xs text-destructive">
          Proxy dead — cannot reach Reddit. {state.detail ?? ""}
        </div>
      )}
      {state.kind === "disabled" && (
        <div className="border-b bg-muted/50 px-3 py-1.5 text-xs text-muted-foreground">
          Account disabled — re-enable in Settings / Accounts to use this slot.
        </div>
      )}

      {reply ? (
        <div className={cn("grid gap-3 p-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]", dimClass)}>
          <div className="min-w-0 space-y-2">
            <h3
              className="line-clamp-2 text-sm font-semibold text-foreground"
              title={reply.post_title}
            >
              {reply.post_title}
            </h3>
            <blockquote className="line-clamp-4 border-l-2 border-border pl-3 text-xs leading-relaxed text-muted-foreground">
              {reply.comment_text}
            </blockquote>
            <div className="flex flex-wrap items-center gap-3 text-[11px]">
              {reply.comment_url && (
                <a
                  href={reply.comment_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 font-medium text-foreground hover:underline"
                >
                  Open on reddit
                  <ExternalLink className="h-3 w-3" />
                </a>
              )}
              {reply.comment_author && (
                <span className="font-mono text-muted-foreground">u/{reply.comment_author}</span>
              )}
              <span className="text-muted-foreground">↑{reply.comment_upvotes} cmt</span>
              <span className="text-muted-foreground">↑{reply.post_upvotes} post</span>
            </div>
          </div>

          <div className="min-w-0 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Draft reply
              </span>
              {changed && (
                <span className="text-[10px] font-medium text-amber-700 dark:text-amber-400">Unsaved</span>
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
                <Label
                  htmlFor={`posted-url-${reply.reply_id}`}
                  className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground"
                >
                  Posted reply URL
                </Label>
                {hasPostedUrlInput && !isPostedUrlValid && (
                  <span className="text-[10px] font-medium text-destructive">
                    Not a Reddit comment link
                  </span>
                )}
                {isPostedUrlValid && (
                  <span className="text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
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
                className={cn(
                  "h-9 text-xs",
                  hasPostedUrlInput && !isPostedUrlValid && "border-destructive focus-visible:ring-destructive",
                )}
              />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
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
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => onApprove(reply, editingText)}
                disabled={busy || isLocked || !editingText.trim()}
                title="Approve for the worker to post"
              >
                <Check />
                Approve
              </Button>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => onSave(reply, editingText)}
                disabled={busy || !editingText.trim() || !changed}
                title="Save edits without changing status"
              >
                Save
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="ml-auto text-destructive hover:text-destructive"
                onClick={() => onDismiss(reply)}
                disabled={busy || isLocked}
              >
                <X />
                Dismiss
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <div className="p-6 text-center text-xs text-muted-foreground">
          {state.kind === "active"
            ? "No pending reply for this slot — generate more or scrape new content."
            : "Slot will pick the next pending reply when it becomes available."}
        </div>
      )}

      {overlayInfo && (
        <div
          className={cn(
            "pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-1 bg-background/80 backdrop-blur-[2px]",
            overlayInfo.tone === "amber"
              ? "text-amber-700 dark:text-amber-400"
              : "text-destructive",
          )}
          aria-live="polite"
        >
          <div className="text-[11px] font-semibold uppercase tracking-wider">
            {overlayInfo.label}
          </div>
          <div className="font-mono text-4xl font-bold tabular-nums text-foreground">
            {formatCountdown(overlayInfo.seconds)}
          </div>
          <div className="text-[10px] opacity-80">
            {state.kind === "cooldown" ? "next post unlocks at 0:00" : "resets in"}
          </div>
        </div>
      )}
    </Card>
  );
}
