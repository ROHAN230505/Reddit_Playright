import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


# Reddit comment URL — accept either the canonical /comments/ form or Reddit's
# /r/<sub>/s/<shortcode> share shortlinks (issued by Reddit's mobile/share UI;
# they redirect to a canonical comment permalink).
_REDDIT_COMMENT_URL_RE = re.compile(
    r"^https?://(?:[\w-]+\.)?reddit\.com/"
    r"(?:.*?/comments/[A-Za-z0-9_-]+|(?:r/[\w-]+/)?s/[A-Za-z0-9_-]+)",
    re.IGNORECASE,
)

# GLP thread/post URL — points at a numeric message thread on godlikeproductions.com.
# Canonical shape: /forum1/message{thread_id}/pg{N}#{post_id}
_GLP_THREAD_URL_RE = re.compile(
    r"^https?://(?:www\.)?godlikeproductions\.com/forum\d*/message\d+",
    re.IGNORECASE,
)


class FetchRequest(BaseModel):
    subreddits: list[str] = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=500)


class TrackedSubredditCreate(BaseModel):
    name: str = Field(min_length=1)


class TrackedSubredditItem(BaseModel):
    id: int
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ReplyStatusUpdate(BaseModel):
    status: str | None = None
    reply_text: str | None = Field(default=None, min_length=1)


class ReplyBulkUpdate(BaseModel):
    reply_ids: list[int] = Field(min_length=1)
    status: str | None = None


class ReplyMarkPostedByAccount(BaseModel):
    """Operator manually posted a reply via account_id; record + cooldown.

    `posted_url` is required so the operator can't mark a reply done without
    pasting proof of the posted comment — gates the Live board's Mark done
    action against accidental clicks."""

    account_id: int
    posted_url: str = Field(min_length=1, max_length=1000)
    reply_text: str | None = Field(default=None, min_length=1)

    @field_validator("posted_url")
    @classmethod
    def _validate_comment_url(cls, value: str) -> str:
        v = value.strip()
        if _REDDIT_COMMENT_URL_RE.match(v) or _GLP_THREAD_URL_RE.match(v):
            return v
        raise ValueError(
            "posted_url must be a Reddit comment URL (e.g. "
            "https://www.reddit.com/r/<sub>/comments/<post_id>/.../) or a GLP thread URL "
            "(e.g. https://www.godlikeproductions.com/forum1/message<id>/pg<N>)"
        )


class GenerateRepliesFromExistingRequest(BaseModel):
    subreddits: list[str] | None = None  # None means use all tracked subreddits
    per_sub_limit: int = Field(default=20, ge=1, le=200)
    max_comment_created_at: datetime | None = None  # Only consider comments strictly older than this
    promo_ratio_override: float | None = Field(default=None, ge=0.0, le=1.0)
    skip_judge: bool = False  # Bypass the naturalness judge for promo replies


class ReplyItem(BaseModel):
    reply_id: int
    reply_text: str
    is_ai_relevant: bool
    includes_promo: bool
    status: str
    created_at: datetime
    comment_text: str
    comment_url: str | None
    comment_author: str | None
    comment_upvotes: int
    post_id: int
    post_title: str
    post_body: str | None
    post_url: str
    post_upvotes: int
    post_comment_count: int
    subreddit: str
    # Posting worker fields - optional/additive for backward compatibility.
    target_type: str | None = None
    target_url: str | None = None
    reddit_post_id: str | None = None
    reddit_comment_id: str | None = None
    posting_attempts: int = 0
    posting_claimed_at: datetime | None = None
    posting_claimed_by: str | None = None
    posting_error: str | None = None
    posted_at: datetime | None = None
    posted_reddit_comment_id: str | None = None
    posted_url: str | None = None
    # Multi-platform fields ('reddit' or 'glp'); reddit_* mirrors above for backward compat.
    platform: str = "reddit"
    platform_post_id: str | None = None
    platform_comment_id: str | None = None
    platform_section: str | None = None
    posted_platform_comment_id: str | None = None

    model_config = {"from_attributes": True}


class ReplySummaryItem(BaseModel):
    """Lightweight reply projection for the dashboard analytics/feed views.

    Holds only the fields the Posted analytics and recently-posted feed read.
    Every field lives on the Reply row itself, so the summary endpoint avoids
    the comment/post JOIN and the multi-megabyte payload of full ReplyItems.
    """

    reply_id: int
    reply_text: str
    includes_promo: bool
    status: str
    created_at: datetime
    subreddit: str | None = None
    posted_at: datetime | None = None
    posted_url: str | None = None
    platform: str = "reddit"
    platform_section: str | None = None


class ContentCommentItem(BaseModel):
    id: int
    text: str
    author: str | None
    comment_url: str | None
    upvotes: int
    created_at: datetime


class ContentPostItem(BaseModel):
    id: int
    title: str
    body: str | None
    url: str
    upvotes: int
    number_of_comments: int
    created_at: datetime
    top_comments: list[ContentCommentItem]


class SubredditContentResponse(BaseModel):
    subreddit: str
    page: int
    page_size: int
    total_posts: int
    post_count: int
    comment_count: int
    posts: list[ContentPostItem]


class ScrapeRunItem(BaseModel):
    id: int
    subreddit: str
    source: str
    limit: int
    status: str
    apify_run_id: str | None
    posts_count: int
    comments_count: int
    replies_count: int
    error_message: str | None
    triggered_by: str | None
    created_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class ScrapeRunListResponse(BaseModel):
    page: int
    page_size: int
    total_runs: int
    runs: list[ScrapeRunItem]


class DashboardSummary(BaseModel):
    total_subreddits: int
    total_posts: int
    total_comments: int
    reply_counts: dict[str, int]
    promo_replies: int
    normal_replies: int
    promo_ratio: float
    latest_scrape_time: datetime | None
    latest_scrape_errors: list[ScrapeRunItem]
    worker_counts: dict[str, int]


class DashboardSearchResult(BaseModel):
    kind: str
    id: int
    subreddit: str
    title: str
    text: str
    url: str | None = None
    status: str | None = None
    includes_promo: bool | None = None
    created_at: datetime


class SubredditHealthItem(BaseModel):
    subreddit: str
    total_posts: int
    total_comments: int
    pending_replies: int
    done_replies: int
    promo_replies: int
    latest_scrape_time: datetime | None
    latest_scrape_status: str | None
    error_count: int


class OpportunityReplyItem(BaseModel):
    reply_id: int
    comment_text: str
    comment_url: str | None
    comment_author: str | None
    comment_upvotes: int
    reply_text: str
    includes_promo: bool
    created_at: datetime
    value_score: int


class OpportunityPostItem(BaseModel):
    post_id: int
    subreddit: str
    post_title: str
    post_body: str | None
    post_url: str
    post_upvotes: int
    post_comment_count: int
    post_created_at: datetime
    promotable_replies: list[OpportunityReplyItem]
    normal_replies: list[OpportunityReplyItem]
    promotable_count: int
    normal_count: int
    opportunity_score: int


class SubredditOpportunityResponse(BaseModel):
    subreddit: str
    page: int
    page_size: int
    total_posts: int
    posts: list[OpportunityPostItem]


class WorkerClaimRequest(BaseModel):
    worker_name: str = Field(min_length=1, max_length=255)
    stale_after_seconds: int = Field(default=600, ge=30, le=86400)
    account_id: int | None = None
    # Optional platform scope. When set, the claim only hands out jobs for this
    # platform — used to run a worker dedicated to one platform (e.g. a chan-only
    # worker that must never touch Reddit/GLP replies).
    platform: str | None = Field(default=None, pattern=r"^(reddit|glp|chan)$")


class WorkerJobItem(BaseModel):
    reply_id: int
    reply_text: str
    target_type: str
    target_url: str
    subreddit: str | None
    reddit_post_id: str | None
    reddit_comment_id: str | None
    status: str
    posting_attempts: int
    posting_claimed_at: datetime | None
    posting_claimed_by: str | None
    approved_at: datetime | None
    created_at: datetime
    # Multi-platform fields (platform='reddit' default; 'glp' for GLP jobs).
    platform: str = "reddit"
    platform_post_id: str | None = None
    platform_comment_id: str | None = None
    platform_section: str | None = None

    model_config = {"from_attributes": True}


class WorkerMarkPostedRequest(BaseModel):
    worker_name: str = Field(min_length=1, max_length=255)
    posted_reddit_comment_id: str | None = None
    posted_platform_comment_id: str | None = None
    posted_url: str | None = None


class WorkerMarkFailedRequest(BaseModel):
    worker_name: str = Field(min_length=1, max_length=255)
    error: str = Field(min_length=1, max_length=4000)
    requeue: bool = True


# --- Proxies ---


class ProxyCreate(BaseModel):
    label: str = Field(min_length=1, max_length=255)
    scheme: str = Field(default="http", pattern=r"^(http|https|socks5)$")
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = None
    notes: str | None = None
    skip_validation: bool = False


class ProxyUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=255)
    scheme: str | None = Field(default=None, pattern=r"^(http|https|socks5)$")
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = None
    password: str | None = None
    status: str | None = Field(default=None, pattern=r"^(ACTIVE|DISABLED|FAILED)$")
    notes: str | None = None
    revalidate: bool = False


class ProxyItem(BaseModel):
    id: int
    label: str
    scheme: str
    host: str
    port: int
    username: str | None
    has_password: bool
    status: str
    notes: str | None
    account_count: int
    last_checked_at: datetime | None
    last_check_error: str | None
    last_check_ip: str | None
    created_at: datetime


class ProxyValidationResult(BaseModel):
    ok: bool
    ip: str | None = None
    error: str | None = None


# --- Reddit accounts ---


class RedditAccountCreate(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1)
    totp_secret: str | None = None
    proxy_id: int | None = None
    profile_index: int | None = Field(default=None, ge=0, le=5)
    posts_per_hour_limit: int | None = Field(default=None, ge=1, le=200)
    posts_per_day_limit: int | None = Field(default=None, ge=1, le=2000)
    min_seconds_between_posts: int | None = Field(default=None, ge=10, le=86400)
    max_seconds_between_posts: int | None = Field(default=None, ge=10, le=86400)
    platform: str = Field(default="reddit", pattern=r"^(reddit|glp|chan)$")


class RedditAccountUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=1)
    totp_secret: str | None = None
    proxy_id: int | None = None
    is_enabled: bool | None = None
    status: str | None = None
    profile_index: int | None = Field(default=None, ge=0, le=5)
    posts_per_hour_limit: int | None = Field(default=None, ge=1, le=200)
    posts_per_day_limit: int | None = Field(default=None, ge=1, le=2000)
    min_seconds_between_posts: int | None = Field(default=None, ge=10, le=86400)
    max_seconds_between_posts: int | None = Field(default=None, ge=10, le=86400)
    assigned_subreddits: list[str] | None = None
    assigned_sections: list[str] | None = None


class RedditAccountItem(BaseModel):
    id: int
    username: str
    has_totp: bool
    proxy_id: int | None
    proxy_label: str | None
    status: str
    is_enabled: bool
    last_login_at: datetime | None
    last_seen_at: datetime | None
    last_action: str | None
    last_error: str | None
    user_data_dir: str | None
    has_cookies: bool = False
    cookies_set_at: datetime | None = None
    profile_index: int = 0
    profile_summary: str | None = None
    posts_per_hour_limit: int = 4
    posts_per_day_limit: int = 30
    min_seconds_between_posts: int = 300
    max_seconds_between_posts: int = 900
    next_eligible_at: datetime | None = None
    assigned_subreddits: list[str] = Field(default_factory=list)
    platform: str = "reddit"
    assigned_sections: list[str] = Field(default_factory=list)
    created_at: datetime


class RedditAccountSecret(BaseModel):
    """Worker-only payload — includes decrypted password and TOTP secret + profile."""

    id: int
    username: str
    password: str
    totp_secret: str | None
    proxy: dict | None
    user_data_dir: str
    is_enabled: bool
    status: str
    session_cookies: list[dict] | None = None
    profile: dict | None = None  # {user_agent, viewport_width, viewport_height, timezone_id, locale, device_scale_factor}
    platform: str = "reddit"


class RedditAccountCookies(BaseModel):
    raw: str = Field(min_length=1, max_length=200_000)


class RedditAccountHeartbeat(BaseModel):
    last_action: str = Field(min_length=1, max_length=255)
    status: str | None = Field(default=None, max_length=30)
    last_error: str | None = Field(default=None, max_length=4000)


class SubredditAssignment(BaseModel):
    account_id: int
    username: str
    profile_index: int
    subreddits: list[str]
    posts_last_7d: int  # sum across the assigned subreddits


class AutoAssignSubredditsResponse(BaseModel):
    assignments: list[SubredditAssignment]
    unassigned_subreddits: list[str]  # tracked subs with no enabled account
    total_subreddits: int


class RedditAccountActivity(BaseModel):
    account_id: int
    username: str
    posts_last_hour: int
    posts_last_day: int
    posts_per_hour_limit: int
    posts_per_day_limit: int
    last_posted_at: datetime | None
    next_eligible_at: datetime | None
    seconds_until_eligible: int
    is_in_cooldown: bool
    is_at_hourly_limit: bool
    is_at_daily_limit: bool
    recent_posts: list[dict]  # [{reply_id, posted_at, subreddit, reply_text_preview}]
    last_failed_post: dict | None = None


class RedditAccountHealthItem(BaseModel):
    account: RedditAccountItem
    activity: RedditAccountActivity


class RedditAccountHealthResponse(BaseModel):
    accounts: list[RedditAccountItem]
    activity: dict[int, RedditAccountActivity]
    items: list[RedditAccountHealthItem]
