from datetime import datetime

from pydantic import BaseModel, Field


class FetchRequest(BaseModel):
    subreddits: list[str] = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=500)


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
    post_id: int
    post_title: str
    post_url: str
    subreddit: str

    model_config = {"from_attributes": True}
