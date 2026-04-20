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

    comment: Mapped["Comment"] = relationship("Comment", back_populates="replies")


class TrackedSubreddit(Base):
    __tablename__ = "tracked_subreddits"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
