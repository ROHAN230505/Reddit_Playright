from datetime import datetime

from pydantic import BaseModel, Field


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
    status: str


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
    # Posting worker fields — optional/additive for backward compatibility.
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

    model_config = {"from_attributes": True}


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

    model_config = {"from_attributes": True}


class WorkerMarkPostedRequest(BaseModel):
    worker_name: str = Field(min_length=1, max_length=255)
    posted_reddit_comment_id: str | None = None


class WorkerMarkFailedRequest(BaseModel):
    worker_name: str = Field(min_length=1, max_length=255)
    error: str = Field(min_length=1, max_length=4000)
    requeue: bool = True
