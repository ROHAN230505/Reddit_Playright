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
    post_count: int
    comment_count: int
    posts: list[ContentPostItem]
