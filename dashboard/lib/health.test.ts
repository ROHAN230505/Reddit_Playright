import { describe, expect, it } from "vitest";
import { accountIsPostable, displayStatus, isBanned, sessionCaption } from "./health";
import type { RedditAccountItem } from "./api";

function acct(partial: Partial<RedditAccountItem>): RedditAccountItem {
  return {
    id: 11,
    username: "destruct_noob",
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
    ...partial,
  };
}

describe("reddit health display", () => {
  it("treats sticky BANNED status as banned even if health is HEALTHY", () => {
    const a = acct({ status: "BANNED", reddit_health: "HEALTHY", reddit_session_alive: true, is_enabled: false });
    expect(isBanned(a)).toBe(true);
    expect(displayStatus(a)).toBe("BANNED");
    expect(accountIsPostable(a)).toBe(false);
    expect(sessionCaption(a)).toMatch(/still logged in/i);
  });

  it("treats reddit_health BANNED as banned even if status is still ACTIVE", () => {
    const a = acct({ status: "ACTIVE", reddit_health: "BANNED", reddit_session_alive: true });
    expect(isBanned(a)).toBe(true);
    expect(displayStatus(a)).toBe("BANNED");
    expect(accountIsPostable(a)).toBe(false);
    expect(sessionCaption(a)).toMatch(/still logged in/i);
  });

  it("does not treat a live session as postable when health is UNKNOWN", () => {
    const a = acct({ status: "ACTIVE", reddit_health: "UNKNOWN", reddit_session_alive: true, is_enabled: true });
    expect(isBanned(a)).toBe(false);
    expect(displayStatus(a)).toBe("ACTIVE");
    expect(sessionCaption(a)).toBe("session alive");
    expect(accountIsPostable(a)).toBe(false);
  });

  it("is postable only when enabled, ACTIVE, and HEALTHY", () => {
    const a = acct({ status: "ACTIVE", reddit_health: "HEALTHY", reddit_session_alive: true, is_enabled: true });
    expect(isBanned(a)).toBe(false);
    expect(displayStatus(a)).toBe("ACTIVE");
    expect(sessionCaption(a)).toBe("session alive");
    expect(accountIsPostable(a)).toBe(true);
  });
});
