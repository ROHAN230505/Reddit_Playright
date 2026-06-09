// Client for the Instagram (doomscroller) service, consumed by the native
// Instagram dashboard section. All calls go to the same-origin Next.js proxy at
// /api/instagram/* (see app/api/instagram/[...path]/route.ts), which forwards to
// the internal IG service and is protected by the dashboard session middleware.

const IG = "/api/instagram";

export type IgQueueCounts = Record<string, number>;

export type IgThread = {
  id: number;
  instagram_thread_id: string;
  participant_usernames: string[] | Record<string, unknown> | null;
  last_message_at: string | null;
  is_read: boolean;
  priority_queue: string | null;
  unread_count: number;
};

export type IgMessage = {
  id: number;
  sender_username: string;
  text: string | null;
  media_url: string | null;
  timestamp: string;
  is_inbound: boolean;
};

export type IgComment = {
  id: number;
  instagram_comment_id: string;
  username: string;
  text: string;
  timestamp: string;
  is_replied: boolean;
  priority_queue: string | null;
};

export type IgApproval = {
  id: number;
  pending_action_id: number;
  status: string;
  reviewer_notes: string | null;
  screenshot_path: string | null;
  created_at: string;
  // Some IG builds enrich approvals with action context; keep these optional.
  action_type?: string;
  proposed_text?: string;
  target_id?: string;
  risk_level?: string;
  risk_flags?: string[];
  expires_at?: string;
};

export type IgActionLog = {
  id: number;
  action_type: string;
  success: boolean;
  error_message: string | null;
  executed_at: string;
};

export type IgCuratorPack = {
  pack_id: string;
  label: string;
  enabled: boolean;
  interval_minutes: number;
  allow_public_actions: boolean;
  hashtag_count?: number;
  last_status: string | null;
  last_run_finished_at: string | null;
  last_run_age?: string | null;
  last_error_summary?: string | null;
};

export type IgCuratorRun = {
  id: number;
  pack_id: string;
  account_id: number;
  status: string;
  trigger_source?: string;
  started_at: string;
  finished_at: string | null;
  search_count: number;
  browse_count: number;
  watch_reel_count: number;
  like_count: number;
  save_count: number;
  follow_count: number;
  public_action_suggestion_count: number;
};

export type IgPublicActionStat = {
  account_id: number;
  username: string;
  posts_last_hour: number;
  posts_last_day: number;
  hourly_cap: number;
  daily_cap: number;
  hour_remaining: number;
  day_remaining: number;
};

export type IgAccount = {
  id: number;
  username: string;
  display_name: string | null;
  enabled: boolean;
  deleted_at: string | null;
  is_logged_in: boolean;
  proxy_server: string | null;
  user_agent: string | null;
  created_via: string | null;
  notes: string | null;
  created_at: string | null;
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${IG}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Instagram request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const igApi = {
  queues: () => req<{ queues: IgQueueCounts }>("/queues"),
  threads: (limit = 20, queue?: string) => {
    const p = new URLSearchParams({ limit: String(limit) });
    if (queue) p.set("queue", queue);
    return req<{ threads: IgThread[] }>(`/threads?${p}`);
  },
  thread: (id: number, limit = 50) =>
    req<{ thread_id: number; messages: IgMessage[] }>(`/threads/${id}?limit=${limit}`),
  comments: (limit = 20, queue?: string) => {
    const p = new URLSearchParams({ limit: String(limit) });
    if (queue) p.set("queue", queue);
    return req<{ comments: IgComment[] }>(`/comments?${p}`);
  },
  approvals: (status = "waiting", limit = 50) =>
    req<{ approvals: IgApproval[] }>(`/approvals?status=${status}&limit=${limit}`),
  reviewApproval: (id: number, decision: "approve" | "reject", reviewerNotes = "") =>
    req<{ approval_id: number; decision: string; status: string }>(
      `/approvals/${id}/review`,
      { method: "POST", body: JSON.stringify({ decision, reviewer_notes: reviewerNotes }) },
    ),
  executeApproval: (id: number) =>
    req<Record<string, unknown>>(`/approvals/${id}/execute`, { method: "POST" }),
  actions: (limit = 25) => req<{ actions: IgActionLog[] }>(`/actions?limit=${limit}`),
  curatorPacks: () => req<{ packs: IgCuratorPack[] }>("/curator/packs"),
  curatorRuns: (packId?: string, limit = 20) => {
    const p = new URLSearchParams({ limit: String(limit) });
    if (packId) p.set("pack_id", packId);
    return req<{ runs: IgCuratorRun[] }>(`/curator/runs?${p}`);
  },
  accounts: (includeDisabled = true) =>
    req<{ accounts: IgAccount[] }>(`/accounts?include_disabled=${includeDisabled}`),
  publicActions: () =>
    req<{ accounts: IgPublicActionStat[] }>("/curator/public-actions"),
};
