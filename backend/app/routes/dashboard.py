from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Comment, Post, Reply, ScrapeRun, TrackedSubreddit
from app.db.session import get_db
from app.schemas import DashboardSearchResult, DashboardSummary, SubredditHealthItem

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(db: Session = Depends(get_db)):
    total_subreddits = db.scalar(select(func.count(TrackedSubreddit.id))) or 0
    total_posts = db.scalar(select(func.count(Post.id))) or 0
    total_comments = db.scalar(select(func.count(Comment.id))) or 0

    reply_counts = {
        status: count
        for status, count in db.execute(
            select(Reply.status, func.count(Reply.id)).group_by(Reply.status)
        ).all()
    }
    promo_replies = db.scalar(select(func.count(Reply.id)).where(Reply.includes_promo == True)) or 0  # noqa: E712
    normal_replies = db.scalar(select(func.count(Reply.id)).where(Reply.includes_promo == False)) or 0  # noqa: E712
    total_classified = promo_replies + normal_replies

    latest_scrape_time = db.scalar(select(func.max(ScrapeRun.finished_at)))
    if latest_scrape_time is None:
        latest_scrape_time = db.scalar(select(func.max(ScrapeRun.created_at)))

    latest_scrape_errors = db.scalars(
        select(ScrapeRun)
        .where(ScrapeRun.error_message.is_not(None))
        .order_by(ScrapeRun.created_at.desc())
        .limit(5)
    ).all()

    worker_counts = {
        status: reply_counts.get(status, 0)
        for status in ("APPROVED", "POSTING", "POSTED", "FAILED")
    }

    return DashboardSummary(
        total_subreddits=total_subreddits,
        total_posts=total_posts,
        total_comments=total_comments,
        reply_counts=reply_counts,
        promo_replies=promo_replies,
        normal_replies=normal_replies,
        promo_ratio=round(promo_replies / total_classified, 4) if total_classified else 0,
        latest_scrape_time=latest_scrape_time,
        latest_scrape_errors=latest_scrape_errors,
        worker_counts=worker_counts,
    )


@router.get("/search", response_model=list[DashboardSearchResult])
def dashboard_search(
    q: str = Query(min_length=2),
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    pattern = f"%{q.strip()}%"
    results: list[DashboardSearchResult] = []

    posts = db.scalars(
        select(Post)
        .where(or_(Post.title.ilike(pattern), Post.body.ilike(pattern)))
        .order_by(Post.created_at.desc())
        .limit(limit)
    ).all()
    for post in posts:
        results.append(
            DashboardSearchResult(
                kind="post",
                id=post.id,
                subreddit=post.subreddit,
                title=post.title,
                text=post.body or "",
                url=post.url,
                created_at=post.created_at,
            )
        )

    comments = db.scalars(
        select(Comment)
        .join(Post, Comment.post_id == Post.id)
        .where(Comment.text.ilike(pattern))
        .order_by(Comment.created_at.desc())
        .limit(limit)
    ).all()
    for comment in comments:
        post = comment.post
        results.append(
            DashboardSearchResult(
                kind="comment",
                id=comment.id,
                subreddit=post.subreddit,
                title=post.title,
                text=comment.text,
                url=comment.comment_url,
                created_at=comment.created_at,
            )
        )

    replies = db.scalars(
        select(Reply)
        .join(Reply.comment)
        .join(Comment.post)
        .where(Reply.reply_text.ilike(pattern))
        .order_by(Reply.created_at.desc())
        .limit(limit)
    ).all()
    for reply in replies:
        post = reply.comment.post
        results.append(
            DashboardSearchResult(
                kind="reply",
                id=reply.id,
                subreddit=post.subreddit,
                title=post.title,
                text=reply.reply_text,
                url=reply.target_url or reply.comment.comment_url or post.url,
                status=reply.status,
                includes_promo=reply.includes_promo,
                created_at=reply.created_at,
            )
        )

    results.sort(key=lambda item: item.created_at, reverse=True)
    return results[:limit]


@router.get("/subreddit-health", response_model=list[SubredditHealthItem])
def subreddit_health(db: Session = Depends(get_db)):
    tracked = db.scalars(select(TrackedSubreddit).order_by(TrackedSubreddit.name.asc())).all()
    rows: list[SubredditHealthItem] = []
    for item in tracked:
        name = item.name
        lower_name = name.lower()
        total_posts = db.scalar(
            select(func.count(Post.id)).where(func.lower(Post.subreddit) == lower_name)
        ) or 0
        total_comments = db.scalar(
            select(func.count(Comment.id))
            .join(Post, Comment.post_id == Post.id)
            .where(func.lower(Post.subreddit) == lower_name)
        ) or 0
        pending_replies = db.scalar(
            select(func.count(Reply.id))
            .join(Reply.comment)
            .join(Comment.post)
            .where(Reply.status == "PENDING", func.lower(Post.subreddit) == lower_name)
        ) or 0
        done_replies = db.scalar(
            select(func.count(Reply.id))
            .join(Reply.comment)
            .join(Comment.post)
            .where(Reply.status == "DONE", func.lower(Post.subreddit) == lower_name)
        ) or 0
        promo_replies = db.scalar(
            select(func.count(Reply.id))
            .join(Reply.comment)
            .join(Comment.post)
            .where(Reply.includes_promo == True, func.lower(Post.subreddit) == lower_name)  # noqa: E712
        ) or 0
        latest_run = db.scalar(
            select(ScrapeRun)
            .where(func.lower(ScrapeRun.subreddit) == lower_name)
            .order_by(ScrapeRun.created_at.desc())
            .limit(1)
        )
        error_count = db.scalar(
            select(func.count(ScrapeRun.id)).where(
                func.lower(ScrapeRun.subreddit) == lower_name,
                ScrapeRun.error_message.is_not(None),
            )
        ) or 0
        rows.append(
            SubredditHealthItem(
                subreddit=name,
                total_posts=total_posts,
                total_comments=total_comments,
                pending_replies=pending_replies,
                done_replies=done_replies,
                promo_replies=promo_replies,
                latest_scrape_time=latest_run.finished_at or latest_run.created_at if latest_run else None,
                latest_scrape_status=latest_run.status if latest_run else None,
                error_count=error_count,
            )
        )
    return rows
