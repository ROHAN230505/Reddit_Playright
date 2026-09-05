import type {
  AccountActivity,
  BrandConfig,
  RedditAccountItem,
  ReplyItem,
} from "@/lib/api";

export const MIN_SLOT_COUNT = 10;
// When one sub accounts for >SWAMPED_THRESHOLD of an account's unused PENDING
// pool, the slot picker also considers replies from subs OUTSIDE the account's
// assigned_subreddits — so the operator isn't stuck cycling through a single
// dominant sub when a generation burst skewed the queue.
export const SWAMPED_THRESHOLD = 0.5;

export type SlotState =
  | { kind: "active" }
  | { kind: "cooldown"; secondsLeft: number }
  | { kind: "hourly"; used: number; cap: number; resetsInSeconds: number }
  | { kind: "daily"; used: number; cap: number; resetsInSeconds: number }
  | { kind: "disabled" }
  | { kind: "banned"; detail: string | null; sessionAlive: boolean | null }
  | { kind: "session_dead"; detail: string | null }
  | { kind: "no_cookies" }
  | { kind: "proxy_dead"; detail: string | null };

export type AssignedSlot = {
  slot: number;
  slotPosition: number;
  slotTotal: number;
  account: RedditAccountItem | null;
  reply: ReplyItem | null;
};

// Backend returns naive datetimes (no TZ suffix) from datetime.utcnow().
// Browsers parse those as LOCAL time, which silently breaks countdowns
// for any timezone other than UTC. Force UTC interpretation.
export function parseServerUtc(value: string): number {
  if (/Z$/.test(value) || /[+-]\d{2}:?\d{2}$/.test(value)) {
    return new Date(value).getTime();
  }
  return new Date(value + "Z").getTime();
}

export function formatCountdown(seconds: number): string {
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

export function deriveSlotState(
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

function statusRank(acc: RedditAccountItem) {
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
}

export function assignQueueSlots({
  accounts,
  pending,
  activity,
  brands,
}: {
  accounts: RedditAccountItem[];
  pending: ReplyItem[];
  activity: Record<number, AccountActivity>;
  brands: BrandConfig[];
}): AssignedSlot[] {
  const redditAccounts = accounts.filter(
    (account) => (account.platform || "reddit") === "reddit",
  );
  const slotCount = Math.max(
    MIN_SLOT_COUNT,
    ...redditAccounts.map((a) => (a.profile_index ?? 0) + 1),
  );
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
  const allAssignedSubs = new Set<string>();
  for (const acc of redditAccounts) {
    if (!acc.is_enabled) continue;
    for (const s of acc.assigned_subreddits ?? []) {
      const lower = s.toLowerCase();
      if (lower) allAssignedSubs.add(lower);
    }
  }
  const usedReplyIds = new Set<number>();
  const result: AssignedSlot[] = [];
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
        const next = pending.find(
          (r) => !usedReplyIds.has(r.reply_id) && replyMatchesAccount(r, account),
        );
        if (next) {
          reply = next;
          usedReplyIds.add(next.reply_id);
        }
      } else {
        const lastPostBySub = new Map<string, number>();
        const acctActivity = activity[account.id];
        for (const post of acctActivity?.recent_posts ?? []) {
          if (!post.subreddit || !post.posted_at) continue;
          const s = post.subreddit.toLowerCase();
          const ms = parseServerUtc(post.posted_at);
          const cur = lastPostBySub.get(s);
          if (cur === undefined || ms > cur) lastPostBySub.set(s, ms);
        }

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

        let chosen: ReplyItem | null = null;
        for (const sub of rankCandidateSubs(assignedBySub)) {
          const list = assignedBySub.get(sub);
          if (list && list.length) {
            chosen = list[0];
            break;
          }
        }

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
    result.push({ slot, slotPosition, slotTotal, account, reply });
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
}
