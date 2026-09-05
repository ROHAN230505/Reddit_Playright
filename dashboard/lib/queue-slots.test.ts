import { describe, expect, it } from "vitest";
import type { AccountActivity, BrandConfig, RedditAccountItem, ReplyItem } from "./api";
import {
  MIN_SLOT_COUNT,
  assignQueueSlots,
  deriveSlotState,
  formatCountdown,
  parseServerUtc,
} from "./queue-slots";

function acct(partial: Partial<RedditAccountItem> & { id: number; username: string }): RedditAccountItem {
  return {
    status: "ACTIVE",
    has_totp: false,
    proxy_id: null,
    proxy_label: null,
    is_enabled: true,
    last_login_at: null,
    last_seen_at: null,
    last_action: null,
    last_error: null,
    user_data_dir: null,
    created_at: "2026-01-01T00:00:00Z",
    profile_index: 0,
    assigned_subreddits: [],
    platform: "reddit",
    reddit_health: "HEALTHY",
    ...partial,
  };
}

function reply(partial: Partial<ReplyItem> & { reply_id: number; subreddit: string }): ReplyItem {
  return {
    reply_text: `draft ${partial.reply_id}`,
    is_ai_relevant: true,
    includes_promo: false,
    status: "PENDING",
    created_at: "2026-01-01T00:00:00Z",
    comment_text: "comment",
    comment_url: null,
    comment_author: "op",
    comment_upvotes: 1,
    post_id: 1,
    post_title: "title",
    post_body: null,
    post_url: "https://reddit.com",
    post_upvotes: 1,
    post_comment_count: 1,
    platform: "reddit",
    ...partial,
  };
}

const noActivity: Record<number, AccountActivity> = {};
const brands: BrandConfig[] = [];

describe("parseServerUtc / formatCountdown", () => {
  it("treats naive timestamps as UTC", () => {
    expect(parseServerUtc("2026-01-01T00:00:00")).toBe(Date.parse("2026-01-01T00:00:00Z"));
  });

  it("formats hours when the wait is long", () => {
    expect(formatCountdown(3661)).toBe("1:01:01");
    expect(formatCountdown(75)).toBe("1:15");
  });
});

describe("deriveSlotState", () => {
  it("prefers public BANNED over a live session", () => {
    const state = deriveSlotState(
      acct({
        id: 1,
        username: "banned",
        reddit_health: "BANNED",
        reddit_session_alive: true,
      }),
      undefined,
      Date.now(),
    );
    expect(state.kind).toBe("banned");
  });

  it("unlocks when cooldown has elapsed", () => {
    const now = Date.parse("2026-01-01T00:01:00Z");
    const activity: AccountActivity = {
      account_id: 1,
      username: "a",
      posts_last_hour: 0,
      posts_last_day: 0,
      posts_per_hour_limit: 2,
      posts_per_day_limit: 12,
      last_posted_at: "2026-01-01T00:00:00Z",
      next_eligible_at: "2026-01-01T00:00:30Z",
      seconds_until_eligible: 0,
      is_in_cooldown: true,
      is_at_hourly_limit: false,
      is_at_daily_limit: false,
      recent_posts: [],
    };
    expect(deriveSlotState(acct({ id: 1, username: "a" }), activity, now).kind).toBe("active");
  });
});

describe("assignQueueSlots", () => {
  it("renders empty slots up to the minimum when there are no accounts", () => {
    const slots = assignQueueSlots({
      accounts: [],
      pending: [],
      activity: noActivity,
      brands,
    });
    expect(slots).toHaveLength(MIN_SLOT_COUNT);
    expect(slots.every((slot) => slot.account === null && slot.reply === null)).toBe(true);
  });

  it("gives each account a distinct pending reply matching its assigned sub", () => {
    const accounts = [
      acct({
        id: 1,
        username: "one",
        profile_index: 0,
        assigned_subreddits: ["alpha", "gamma"],
      }),
      acct({ id: 2, username: "two", profile_index: 1, assigned_subreddits: ["beta"] }),
    ];
    const pending = [
      reply({ reply_id: 10, subreddit: "alpha" }),
      reply({ reply_id: 20, subreddit: "gamma" }),
      reply({ reply_id: 11, subreddit: "beta" }),
    ];
    const slots = assignQueueSlots({ accounts, pending, activity: noActivity, brands });
    const filled = slots.filter((slot) => slot.account);
    expect(filled).toHaveLength(2);
    const replyIds = filled.map((slot) => slot.reply?.reply_id);
    expect(replyIds.every((id) => typeof id === "number")).toBe(true);
    expect(new Set(replyIds).size).toBe(2);
  });

  it("escapes a swamped assigned sub into an orphan sub", () => {
    const accounts = [
      acct({ id: 1, username: "one", profile_index: 0, assigned_subreddits: ["alpha"] }),
    ];
    const pending = [
      reply({ reply_id: 1, subreddit: "alpha" }),
      reply({ reply_id: 2, subreddit: "alpha" }),
      reply({ reply_id: 3, subreddit: "alpha" }),
      reply({ reply_id: 4, subreddit: "orphan" }),
    ];
    const slots = assignQueueSlots({ accounts, pending, activity: noActivity, brands });
    expect(slots[0]?.reply?.subreddit).toBe("orphan");
  });
});
