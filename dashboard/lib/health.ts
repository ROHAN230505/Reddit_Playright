import type { RedditAccountItem } from "@/lib/api";

export function isBanned(account: Pick<RedditAccountItem, "status" | "reddit_health">): boolean {
  return account.status === "BANNED" || account.reddit_health === "BANNED";
}

export function displayStatus(account: RedditAccountItem): RedditAccountItem["status"] {
  if (isBanned(account)) return "BANNED";
  return account.status;
}

export function accountIsPostable(account: RedditAccountItem): boolean {
  if (!account.is_enabled) return false;
  if (isBanned(account)) return false;
  if (account.status !== "ACTIVE") return false;
  if (account.reddit_health && account.reddit_health !== "HEALTHY") return false;
  return true;
}

export function sessionCaption(account: RedditAccountItem): string {
  if (account.reddit_session_alive === true) {
    return isBanned(account) ? "still logged in — cannot post" : "session alive";
  }
  if (account.reddit_session_alive === false) return "session not authenticated";
  return "session n/a";
}

export function realtimeVisible(account: RedditAccountItem): boolean {
  const platform = account.platform || "reddit";
  if (platform !== "reddit") return false;
  return true;
}
