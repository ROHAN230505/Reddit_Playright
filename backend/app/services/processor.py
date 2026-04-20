import random
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Comment, Post, Reply
from app.services.apify_service import fetch_subreddit
from app.services.deepseek_service import deepseek_call


def normalize_comment(raw: dict, fallback_post_url: str | None = None) -> dict:
    return {
        "text": raw.get("text", "") or raw.get("body", "") or "",
        "comment_url": raw.get("url") or raw.get("commentUrl"),
        "post_url": raw.get("postUrl") or fallback_post_url,
        "author": raw.get("author"),
        "created_at": _parse_datetime(raw.get("createdAt")),
    }


def classify_ai_relevance(text: str) -> bool:
    prompt = f"""
Return ONLY YES or NO.
Is this related to AI, LLMs, automation, SaaS tools?
{text}
"""
    response = deepseek_call(prompt)
    return response.strip().upper() == "YES"


def should_insert_promo() -> bool:
    return random.random() < 0.5


def generate_reply(comment: str, include_promo: bool) -> str:
    promo = ""
    if include_promo:
        promo = """
- Subtly mention sentx.ai if relevant
- Do NOT sound promotional
"""
    prompt = f"""
Write a natural Reddit reply.
Rules:
- Human tone
- Helpful
- Max 4 lines
- No marketing language
{promo}
Comment:
{comment}
"""
    return deepseek_call(prompt).strip()


def process_subreddit(db: Session, subreddit: str, limit: int = 50) -> dict:
    posts = fetch_subreddit(subreddit, limit=limit)
    stats = {"posts": 0, "comments": 0, "replies": 0}

    for raw_post in posts:
        post = save_post(db, subreddit, raw_post)
        stats["posts"] += 1

        for raw_comment in iter_comments(raw_post):
            comment_payload = normalize_comment(raw_comment, fallback_post_url=post.url)
            if not comment_payload["text"].strip():
                continue

            stats["comments"] += 1
            if not classify_ai_relevance(comment_payload["text"]):
                continue

            comment = save_comment(db, post.id, comment_payload)
            include_promo = should_insert_promo()
            reply_text = generate_reply(comment.text, include_promo)
            save_reply(
                db,
                comment_id=comment.id,
                reply_text=reply_text,
                is_ai_relevant=True,
                includes_promo=include_promo,
            )
            stats["replies"] += 1

    return stats


def save_post(db: Session, subreddit: str, raw_post: dict) -> Post:
    url = raw_post.get("url") or raw_post.get("postUrl")
    if not url:
        raise ValueError("Post is missing a URL.")

    existing = db.scalar(select(Post).where(Post.url == url))
    if existing:
        return existing

    post = Post(
        subreddit=subreddit,
        title=raw_post.get("title", "Untitled Post"),
        url=url,
        created_at=_parse_datetime(raw_post.get("createdAt")) or datetime.utcnow(),
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


def save_comment(db: Session, post_id: int, payload: dict) -> Comment:
    stmt = select(Comment).where(
        Comment.post_id == post_id,
        Comment.text == payload["text"],
        Comment.comment_url == payload["comment_url"],
    )
    existing = db.scalar(stmt)
    if existing:
        return existing

    comment = Comment(
        post_id=post_id,
        text=payload["text"],
        comment_url=payload["comment_url"],
        post_url=payload["post_url"],
        author=payload["author"],
        created_at=payload["created_at"] or datetime.utcnow(),
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def save_reply(
    db: Session,
    comment_id: int,
    reply_text: str,
    is_ai_relevant: bool,
    includes_promo: bool,
    status: str = "PENDING",
) -> Reply:
    reply = Reply(
        comment_id=comment_id,
        reply_text=reply_text,
        is_ai_relevant=is_ai_relevant,
        includes_promo=includes_promo,
        status=status,
    )
    db.add(reply)
    db.commit()
    db.refresh(reply)
    return reply


def iter_comments(raw_post: dict) -> Iterable[dict]:
    comments = raw_post.get("comments") or []
    if isinstance(comments, list):
        return comments
    return []


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
