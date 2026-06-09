from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    subreddit: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(500))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(String(1000), unique=True, index=True)
    upvotes: Mapped[int] = mapped_column(Integer, default=0)
    number_of_comments: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    comments: Mapped[list["Comment"]] = relationship(
        "Comment", back_populates="post", cascade="all, delete-orphan"
    )


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    comment_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    post_url: Mapped[str] = mapped_column(String(1000))
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    upvotes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    post: Mapped["Post"] = relationship("Post", back_populates="comments")
    replies: Mapped[list["Reply"]] = relationship(
        "Reply", back_populates="comment", cascade="all, delete-orphan"
    )


class Reply(Base):
    __tablename__ = "replies"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    comment_id: Mapped[int] = mapped_column(ForeignKey("comments.id"), index=True)
    reply_text: Mapped[str] = mapped_column(Text)
    is_ai_relevant: Mapped[bool] = mapped_column(Boolean, default=False)
    includes_promo: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Playwright posting worker fields (additive; nullable for backward compatibility)
    target_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    target_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    reddit_post_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    reddit_comment_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    subreddit: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # Platform identifier for multi-platform posting: 'reddit' (default) or 'glp'.
    platform: Mapped[str] = mapped_column(String(16), default="reddit", index=True)
    # Generic platform target IDs (used for GLP and any future platform; Reddit
    # continues to use the reddit_* columns above for backwards compatibility).
    platform_post_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    platform_comment_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    platform_section: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    posting_attempts: Mapped[int] = mapped_column(Integer, default=0)
    posting_claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    posting_claimed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    posting_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    posted_reddit_comment_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    posted_platform_comment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    posted_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    posting_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("reddit_accounts.id"), nullable=True, index=True
    )

    comment: Mapped["Comment"] = relationship("Comment", back_populates="replies")
    posting_account: Mapped["RedditAccount | None"] = relationship(
        "RedditAccount", foreign_keys=[posting_account_id]
    )


class Proxy(Base):
    __tablename__ = "proxies"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    label: Mapped[str] = mapped_column(String(255), unique=True)
    scheme: Mapped[str] = mapped_column(String(20), default="http")
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_check_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_check_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    accounts: Mapped[list["RedditAccount"]] = relationship(
        "RedditAccount", back_populates="proxy"
    )


class RedditAccount(Base):
    __tablename__ = "reddit_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_enc: Mapped[str] = mapped_column(Text)
    totp_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    proxy_id: Mapped[int | None] = mapped_column(
        ForeignKey("proxies.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="NEW", index=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_action: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_data_dir: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    session_cookies_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    cookies_set_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Browser-fingerprint slot (0..9). Round-robin assigned at create time.
    profile_index: Mapped[int] = mapped_column(Integer, default=0, index=True)
    # Per-account rate limits (defaults: conservative).
    posts_per_hour_limit: Mapped[int] = mapped_column(Integer, default=4)
    posts_per_day_limit: Mapped[int] = mapped_column(Integer, default=30)
    min_seconds_between_posts: Mapped[int] = mapped_column(Integer, default=300)
    max_seconds_between_posts: Mapped[int] = mapped_column(Integer, default=900)
    # Cooldown timestamp set after each successful post.
    next_eligible_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    # CSV of subreddit names this account is responsible for posting to.
    # Empty/null means "any subreddit". Set via auto-assign or manual edit.
    assigned_subreddits: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Platform this account belongs to: 'reddit' (default) or 'glp'.
    platform: Mapped[str] = mapped_column(String(16), default="reddit", index=True)
    # CSV of section/board filters for non-Reddit platforms (GLP uses tags).
    # Empty/null means "any section".
    assigned_sections: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    proxy: Mapped["Proxy | None"] = relationship("Proxy", back_populates="accounts")


class TrackedSubreddit(Base):
    __tablename__ = "tracked_subreddits"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# Alias for the multi-platform world. The class stays named `RedditAccount` and
# the table stays `reddit_accounts` for backward compatibility; new platform-
# neutral code paths should import `Account` instead.
Account = RedditAccount


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    subreddit: Mapped[str] = mapped_column(String(255), index=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    limit: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="RUNNING", index=True)
    apify_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    posts_count: Mapped[int] = mapped_column(Integer, default=0)
    comments_count: Mapped[int] = mapped_column(Integer, default=0)
    replies_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
