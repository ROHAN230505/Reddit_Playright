const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.BACKEND_BASE_URL ||
  "http://localhost:8000";

export type TrackedSubreddit = {
  id: number;
  name: string;
  created_at: string;
};

export type Platform = "reddit" | "glp" | "chan" | "instagram";

export type ReplyItem = {
  reply_id: number;
  reply_text: string;
  is_ai_relevant: boolean;
  includes_promo: boolean;
  status: string;
  created_at: string;
  comment_text: string;
  comment_url: string | null;
  comment_author: string | null;
  comment_upvotes: number;
  post_id: number;
  post_title: string;
  post_body: string | null;
  post_url: string;
  post_upvotes: number;
  post_comment_count: number;
  subreddit: string;
  target_url?: string | null;
  posting_attempts?: number;
  posting_claimed_by?: string | null;
  posting_error?: string | null;
  posted_at?: string | null;
  posted_url?: string | null;
  platform?: Platform;
  platform_post_id?: string | null;
  platform_comment_id?: string | null;
  platform_section?: string | null;
  posted_platform_comment_id?: string | null;
};

/**
 * Lightweight reply shape returned by `/replies/summary`. Carries only the
 * fields the Posted analytics and recently-posted feed actually read, so the
 * analytics fetch ships ~0.5 MiB instead of ~5 MiB of unused post/comment
 * text. `ReplyItem` is a structural superset, so the full type is still
 * accepted anywhere a `ReplySummary` is expected (homepage, godlike, 4chan).
 */
export type ReplySummary = {
  reply_id: number;
  reply_text: string;
  includes_promo: boolean;
  status: string;
  created_at: string;
  subreddit: string | null;
  posted_at?: string | null;
  posted_url?: string | null;
  platform?: Platform;
  platform_section?: string | null;
};

export type ContentPost = {
  id: number;
  title: string;
  body: string | null;
  url: string;
  upvotes: number;
  number_of_comments: number;
  created_at: string;
  top_comments: {
    id: number;
    text: string;
    author: string | null;
    comment_url: string | null;
    upvotes: number;
    created_at: string;
  }[];
};

export type SubredditContent = {
  subreddit: string;
  page: number;
  page_size: number;
  total_posts: number;
  post_count: number;
  comment_count: number;
  posts: ContentPost[];
};

export type ScrapeRun = {
  id: number;
  subreddit: string;
  source: string;
  limit: number;
  status: string;
  apify_run_id: string | null;
  posts_count: number;
  comments_count: number;
  replies_count: number;
  error_message: string | null;
  triggered_by: string | null;
  created_at: string;
  finished_at: string | null;
};

export type ScrapeRunList = {
  page: number;
  page_size: number;
  total_runs: number;
  runs: ScrapeRun[];
};

export type DashboardSummary = {
  total_subreddits: number;
  total_posts: number;
  total_comments: number;
  reply_counts: Record<string, number>;
  promo_replies: number;
  normal_replies: number;
  promo_ratio: number;
  latest_scrape_time: string | null;
  latest_scrape_errors: ScrapeRun[];
  worker_counts: Record<string, number>;
};

export type DashboardSearchResult = {
  kind: string;
  id: number;
  subreddit: string;
  title: string;
  text: string;
  url: string | null;
  status: string | null;
  includes_promo: boolean | null;
  created_at: string;
};

export type SubredditHealthItem = {
  subreddit: string;
  total_posts: number;
  total_comments: number;
  pending_replies: number;
  done_replies: number;
  promo_replies: number;
  latest_scrape_time: string | null;
  latest_scrape_status: string | null;
  error_count: number;
};

export type ProxyItem = {
  id: number;
  label: string;
  scheme: "http" | "https" | "socks5";
  host: string;
  port: number;
  username: string | null;
  notes: string | null;
  status: "ACTIVE" | "FAILED" | "DISABLED";
  account_count: number;
  last_checked_at: string | null;
  last_check_ip: string | null;
  last_check_error: string | null;
  created_at: string;
};

export type RedditAccountItem = {
  id: number;
  username: string;
  status: "NEW" | "VERIFYING" | "ACTIVE" | "NEEDS_REAUTH" | "FAILED" | "DISABLED";
  has_totp: boolean;
  proxy_id: number | null;
  proxy_label: string | null;
  is_enabled: boolean;
  last_login_at: string | null;
  last_seen_at: string | null;
  last_action: string | null;
  last_error: string | null;
  user_data_dir: string | null;
  created_at: string;
  has_cookies?: boolean;
  cookies_set_at?: string | null;
  // new fields
  profile_index?: number;
  profile_summary?: string | null;
  posts_per_hour_limit?: number;
  posts_per_day_limit?: number;
  min_seconds_between_posts?: number;
  max_seconds_between_posts?: number;
  next_eligible_at?: string | null;
  assigned_subreddits?: string[];
  platform?: Platform;
  assigned_sections?: string[];
};

export type AutoAssignSubredditsResponse = {
  assignments: {
    account_id: number;
    username: string;
    profile_index: number;
    subreddits: string[];
    posts_last_7d: number;
  }[];
  unassigned_subreddits: string[];
  total_subreddits: number;
};

export type AccountActivity = {
  account_id: number;
  username: string;
  posts_last_hour: number;
  posts_last_day: number;
  posts_per_hour_limit: number;
  posts_per_day_limit: number;
  last_posted_at: string | null;
  next_eligible_at: string | null;
  seconds_until_eligible: number;
  is_in_cooldown: boolean;
  is_at_hourly_limit: boolean;
  is_at_daily_limit: boolean;
  recent_posts: Array<{
    reply_id: number;
    posted_at: string | null;
    subreddit: string | null;
    reply_text_preview: string;
    target_url: string | null;
  }>;
  last_failed_post?: {
    reply_id: number;
    status: string;
    failed_at: string | null;
    error: string;
    target_url: string | null;
  } | null;
};

export type AccountHealthResponse = {
  accounts: RedditAccountItem[];
  activity: Record<number, AccountActivity>;
  items: Array<{
    account: RedditAccountItem;
    activity: AccountActivity;
  }>;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  // Proxies
  proxies: () => request<ProxyItem[]>("/proxies"),
  createProxy: (body: {
    label: string;
    scheme: "http" | "https" | "socks5";
    host: string;
    port: number;
    username?: string;
    password?: string;
    notes?: string;
    skip_validation?: boolean;
  }) =>
    fetch(`${API_BASE}/proxies`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    }).then(async (r) => {
      const data = await r.json();
      return { ok: r.ok, status: r.status, data, errorText: r.ok ? "" : JSON.stringify(data) };
    }),
  updateProxy: (id: number, body: { label?: string; scheme?: string; host?: string; port?: number; username?: string; password?: string; notes?: string }) =>
    request<ProxyItem>(`/proxies/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteProxy: (id: number) => request<{ id: number }>(`/proxies/${id}`, { method: "DELETE" }),
  validateProxy: (id: number) =>
    fetch(`${API_BASE}/proxies/${id}/validate`, { method: "POST", cache: "no-store" }).then(async (r) => {
      const data = await r.json();
      return { ok: r.ok, ip: data?.ip ?? null, error: data?.error ?? null };
    }),

  // Accounts
  accounts: () => request<RedditAccountItem[]>("/accounts"),
  accountsHealth: () => request<AccountHealthResponse>("/accounts/health"),
  account: (id: number) => request<RedditAccountItem>(`/accounts/${id}`),
  createAccount: (body: {
    username: string;
    password: string;
    totp_secret?: string;
    proxy_id?: number;
    profile_index?: number;
    posts_per_hour_limit?: number;
    posts_per_day_limit?: number;
    min_seconds_between_posts?: number;
    max_seconds_between_posts?: number;
    platform?: Platform;
  }) =>
    request<RedditAccountItem>("/accounts", { method: "POST", body: JSON.stringify(body) }),
  updateAccount: (id: number, body: {
    password?: string;
    totp_secret?: string;
    proxy_id?: number | null;
    is_enabled?: boolean;
    profile_index?: number;
    posts_per_hour_limit?: number;
    posts_per_day_limit?: number;
    min_seconds_between_posts?: number;
    max_seconds_between_posts?: number;
    assigned_subreddits?: string[];
    assigned_sections?: string[];
  }) =>
    request<RedditAccountItem>(`/accounts/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  autoAssignSubreddits: () =>
    request<AutoAssignSubredditsResponse>("/accounts/auto-assign-subreddits", {
      method: "POST",
    }),
  reverifyAccount: (id: number) =>
    request<RedditAccountItem>(`/accounts/${id}/reverify`, { method: "POST" }),
  uploadCookies: (id: number, raw: string) =>
    fetch(`${API_BASE}/accounts/${id}/cookies`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw }),
      cache: "no-store",
    }).then(async (r) => {
      const data = await r.json();
      return { ok: r.ok, status: r.status, data, errorText: r.ok ? "" : JSON.stringify(data) };
    }),
  clearCookies: (id: number) =>
    request<RedditAccountItem>(`/accounts/${id}/cookies`, { method: "DELETE" }),
  accountActivity: (id: number) => request<AccountActivity>(`/accounts/${id}/activity`),

  // Subreddits
  trackedSubreddits: () => request<TrackedSubreddit[]>("/tracked-subreddits"),
  addSubreddit: (name: string) =>
    request<TrackedSubreddit>("/tracked-subreddits", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  deleteSubreddit: (id: number) => request<{ id: number }>(`/tracked-subreddits/${id}`, { method: "DELETE" }),
  scrapeAll: (limit: number) => request<{ jobs: { subreddit: string; task_id: string }[] }>(`/tracked-subreddits/run?limit=${limit}`, { method: "POST" }),
  scrapeSelected: (subreddit: string, limit: number) =>
    request<{ jobs: { subreddit: string; task_id: string }[] }>("/fetch", {
      method: "POST",
      body: JSON.stringify({ subreddits: [subreddit], limit }),
    }),
  content: (subreddit: string, page: number, pageSize: number, commentLimit: number, dateFrom?: string, dateTo?: string) => {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
      comment_limit: String(commentLimit),
    });
    if (dateFrom) params.set("date_from", new Date(dateFrom).toISOString());
    if (dateTo) params.set("date_to", new Date(`${dateTo}T23:59:59`).toISOString());
    return request<SubredditContent>(`/subreddits/${encodeURIComponent(subreddit)}/content?${params}`);
  },
  triggerGlpScrape: (limit = 30) =>
    request<{ task_id: string; limit: number; auto_approve: boolean }>(
      `/glp/scrape-now?limit=${limit}`,
      { method: "POST" },
    ),
  glpConfig: () => request<{ auto_approve: boolean; topics: string[] }>("/glp/config"),
  triggerChanScrape: (threadsPerBoard?: number) =>
    request<{
      task_id: string;
      boards: string[];
      threads_per_board: number;
      auto_approve: boolean;
    }>(
      `/chan/scrape-now${threadsPerBoard ? `?threads_per_board=${threadsPerBoard}` : ""}`,
      { method: "POST" },
    ),
  chanConfig: () =>
    request<{ auto_approve: boolean; boards: string[]; threads_per_board: number }>(
      "/chan/config",
    ),
  replies: (
    status: string,
    limit = 200,
    subreddit?: string,
    order: "upvotes" | "newest" = "upvotes",
    minPromo?: number,
    platform?: Platform,
  ) => {
    const params = new URLSearchParams({
      status,
      limit: String(limit),
      order,
    });
    if (subreddit && subreddit !== "All") params.set("subreddit", subreddit);
    if (minPromo && minPromo > 0) params.set("min_promo", String(minPromo));
    if (platform) params.set("platform", platform);
    return request<ReplyItem[]>(`/replies?${params}`);
  },
  // Lightweight projection for analytics/feed views — see ReplySummary. Skips
  // the comment/post JOIN and the heavy text fields, so the analytics window
  // loads in a fraction of the time of the full `replies()` payload.
  repliesSummary: (
    status: string,
    limit = 2000,
    platform?: Platform,
    subreddit?: string,
  ) => {
    const params = new URLSearchParams({ status, limit: String(limit) });
    if (platform) params.set("platform", platform);
    if (subreddit && subreddit !== "All") params.set("subreddit", subreddit);
    return request<ReplySummary[]>(`/replies/summary?${params}`);
  },
  updateReply: (replyId: number, payload: { status?: string; reply_text?: string }) =>
    request<{ status: string; reply_id: number }>(`/replies/${replyId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  bulkUpdateReplies: (replyIds: number[], status: string) =>
    request<{ updated: number; status: string }>("/replies/bulk/status", {
      method: "PATCH",
      body: JSON.stringify({ reply_ids: replyIds, status }),
    }),
  generateRepliesFromExisting: (subreddits?: string[], perSubLimit = 20) =>
    request<{
      queued: number;
      per_sub_limit: number;
      jobs: { subreddit: string; task_id: string }[];
    }>("/replies/generate-from-existing", {
      method: "POST",
      body: JSON.stringify({
        subreddits: subreddits ?? null,
        per_sub_limit: perSubLimit,
      }),
    }),
  markReplyPostedByAccount: (
    replyId: number,
    accountId: number,
    postedUrl: string,
    replyText?: string,
  ) =>
    request<{
      reply_id: number;
      status: string;
      posted_at: string | null;
      posted_url: string | null;
      next_eligible_at: string | null;
    }>(`/replies/${replyId}/mark-posted`, {
      method: "POST",
      body: JSON.stringify({
        account_id: accountId,
        posted_url: postedUrl,
        ...(replyText !== undefined ? { reply_text: replyText } : {}),
      }),
    }),
  scrapeRuns: (page: number, pageSize: number, subreddit?: string) => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (subreddit && subreddit !== "All") params.set("subreddit", subreddit);
    return request<ScrapeRunList>(`/scrape-runs?${params}`);
  },
  summary: () => request<DashboardSummary>("/dashboard/summary"),
  search: (query: string) => request<DashboardSearchResult[]>(`/dashboard/search?q=${encodeURIComponent(query)}`),
  subredditHealth: () => request<SubredditHealthItem[]>("/dashboard/subreddit-health"),
  workerQueue: () => request<{ counts: Record<string, number> }>("/worker/queue"),
};
