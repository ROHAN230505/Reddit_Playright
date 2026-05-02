const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.BACKEND_BASE_URL ||
  "http://localhost:8000";

export type TrackedSubreddit = {
  id: number;
  name: string;
  created_at: string;
};

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
  replies: (status: string, limit = 200, subreddit?: string) => {
    const params = new URLSearchParams({ status, limit: String(limit) });
    if (subreddit && subreddit !== "All") params.set("subreddit", subreddit);
    return request<ReplyItem[]>(`/replies?${params}`);
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
