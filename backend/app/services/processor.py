import random
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Comment, Post, Reply, TrackedSubreddit
from app.services.apify_service import fetch_subreddit
from app.services.deepseek_service import deepseek_call

DEFAULT_TRACKED_SUBREDDITS = [
    "ArtificialIntelligence",
    "artificial",
    "AiDeveloperNews",
    "MachineLearning",
    "AIChatReviews",
    "softwareengineer",
    "Automate",
    "technews",
    "technology",
    "tech",
    "AiBuilders",
    "AIToolTesting",
    "AI_Agents",
    "AgentsOfAI",
    "aiagents",
    "singularity",
    "AiAssisted",
    "ArtificialSentience",
    "ChatGPTcomplaints",
    "ChatGPT",
    "Anthropic",
    "ClaudeAI",
    "devworlds",
    "LocalLLaMA",
    "grok",
    "vibecoding",
    "AI_India",
    "ChatGPTCoding",
    "BlackboxAI_",
    "DeepSeek",
    "LocalLLM",
    "LLM",
    "AIToolMadeEasy",
    "LLMDevs",
    "OpenAI",
    "OnlyAICoding",
    "geminiprotocol",
    "OpenSourceAI",
    "AskVibecoders",
]


def normalize_comment(raw: dict, fallback_post_url: str | None = None) -> dict:
    return {
        "text": raw.get("text", "") or raw.get("body", "") or "",
        "comment_url": absolute_reddit_url(raw.get("permalink") or raw.get("url") or raw.get("commentUrl")),
        "post_url": (
            raw.get("postUrl")
            or derive_post_url(raw.get("permalink") or raw.get("url"))
            or fallback_post_url
        ),
        "author": raw.get("author") or raw.get("username"),
        "upvotes": raw.get("score") or raw.get("upVotes") or raw.get("upvotes") or 0,
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
    subreddit = subreddit.strip().removeprefix("r/")
    rows = fetch_subreddit(subreddit, limit=limit)
    stats = {"posts": 0, "comments": 0, "replies": 0}
    current_post: Post | None = None
    posts_by_url: dict[str, Post] = {}

    for row in rows:
        row_type = (row.get("dataType") or row.get("type") or "").lower()
        if row_type == "post":
            current_post = save_post(db, subreddit, row)
            posts_by_url[current_post.url] = current_post
            stats["posts"] += 1
            continue

        if row_type != "comment":
            continue

        comment_payload = normalize_comment(
            row,
            fallback_post_url=current_post.url if current_post else None,
        )
        if not comment_payload["text"].strip():
            continue

        post = resolve_post_for_comment(
            db,
            subreddit=subreddit,
            payload=comment_payload,
            posts_by_url=posts_by_url,
            fallback_post=current_post,
        )
        if not post:
            continue

        comment = save_comment(db, post.id, comment_payload)
        stats["comments"] += 1
        if not classify_ai_relevance(comment_payload["text"]):
            continue

        include_promo = should_insert_promo()
        reply_text = generate_reply(comment.text, include_promo)
        reply = save_reply(
            db,
            comment_id=comment.id,
            reply_text=reply_text,
            is_ai_relevant=True,
            includes_promo=include_promo,
        )
        if reply:
            stats["replies"] += 1

    return stats


def save_post(db: Session, subreddit: str, raw_post: dict) -> Post:
    url = absolute_reddit_url(raw_post.get("url") or raw_post.get("postUrl") or raw_post.get("permalink"))
    if not url:
        raise ValueError("Post is missing a URL.")

    community_name = raw_post.get("subreddit") or raw_post.get("communityName") or f"r/{subreddit}"
    normalized_subreddit = community_name.removeprefix("r/") if community_name else subreddit
    existing = db.scalar(select(Post).where(Post.url == url))
    if existing:
        existing.subreddit = normalized_subreddit
        existing.title = raw_post.get("title") or existing.title
        existing.body = raw_post.get("selfText") or raw_post.get("body") or existing.body
        existing.upvotes = raw_post.get("score") or raw_post.get("upVotes") or raw_post.get("upvotes") or existing.upvotes
        existing.number_of_comments = (
            raw_post.get("numComments")
            or raw_post.get("numberOfComments")
            or raw_post.get("number_of_comments")
            or existing.number_of_comments
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    post = Post(
        subreddit=normalized_subreddit,
        title=raw_post.get("title") or "Untitled Post",
        body=raw_post.get("selfText") or raw_post.get("body"),
        url=url,
        upvotes=raw_post.get("score") or raw_post.get("upVotes") or raw_post.get("upvotes") or 0,
        number_of_comments=(
            raw_post.get("numComments")
            or raw_post.get("numberOfComments")
            or raw_post.get("number_of_comments")
            or 0
        ),
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
        existing.author = payload["author"]
        existing.post_url = payload["post_url"]
        existing.upvotes = payload["upvotes"]
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    comment = Comment(
        post_id=post_id,
        text=payload["text"],
        comment_url=payload["comment_url"],
        post_url=payload["post_url"],
        author=payload["author"],
        upvotes=payload["upvotes"],
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
) -> Reply | None:
    existing = db.scalar(select(Reply).where(Reply.comment_id == comment_id))
    if existing:
        return None

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


def resolve_post_for_comment(
    db: Session,
    subreddit: str,
    payload: dict,
    posts_by_url: dict[str, Post],
    fallback_post: Post | None,
) -> Post | None:
    post_url = payload.get("post_url")
    if post_url and post_url in posts_by_url:
        return posts_by_url[post_url]

    if post_url:
        existing = db.scalar(select(Post).where(Post.url == post_url))
        if existing:
            posts_by_url[post_url] = existing
            return existing

        placeholder = Post(
            subreddit=subreddit.removeprefix("r/"),
            title="Untitled Post",
            url=post_url,
            created_at=datetime.utcnow(),
        )
        db.add(placeholder)
        db.commit()
        db.refresh(placeholder)
        posts_by_url[post_url] = placeholder
        return placeholder

    return fallback_post


def ensure_default_tracked_subreddits(db: Session) -> None:
    existing_names = {
        item.name.lower() for item in db.scalars(select(TrackedSubreddit)).all()
    }
    created = False
    for name in DEFAULT_TRACKED_SUBREDDITS:
        if name.lower() in existing_names:
            continue
        db.add(TrackedSubreddit(name=name))
        created = True
    if created:
        db.commit()


def derive_post_url(url: str | None) -> str | None:
    if not url:
        return None

    parsed = urlparse(absolute_reddit_url(url))
    parts = [part for part in parsed.path.split("/") if part]
    try:
        comments_idx = parts.index("comments")
    except ValueError:
        return url

    if len(parts) < comments_idx + 3:
        return url

    post_path = "/" + "/".join(parts[: comments_idx + 3]) + "/"
    return f"{parsed.scheme}://{parsed.netloc}{post_path}"


def absolute_reddit_url(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return f"https://www.reddit.com{url}"
    return url


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
