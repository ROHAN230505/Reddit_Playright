import random
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, nullslast, select
from sqlalchemy.orm import Session, contains_eager

from app.db.models import Comment, Post, RedditAccount, Reply
from app.db.session import get_db
from app.schemas import (
    GenerateRepliesFromExistingRequest,
    ReplyBulkUpdate,
    ReplyItem,
    ReplyMarkPostedByAccount,
    ReplyStatusUpdate,
    ReplySummaryItem,
)
from app.db.models import TrackedSubreddit
from app.services.processor import generate_reply, should_insert_promo

router = APIRouter(prefix="/replies", tags=["replies"])


@router.get("", response_model=list[ReplyItem])
def get_replies(
    status: str = Query(default="PENDING"),
    subreddit: str | None = Query(default=None),
    platform: str | None = Query(default=None, pattern=r"^(reddit|glp|chan)$"),
    limit: int = Query(default=100, ge=1, le=2000),
    order: str = Query(default="upvotes", pattern=r"^(upvotes|newest)$"),
    min_promo: int = Query(default=0, ge=0, le=2000),
    db: Session = Depends(get_db),
):
    status_upper = status.upper()
    # contains_eager populates reply.comment / comment.post from the rows the
    # JOIN already returns, so the serialization loop below doesn't fire a
    # per-row SELECT for each relationship (N+1). Both are many-to-one, so the
    # JOIN can't multiply rows and `limit` stays exact.
    stmt = (
        select(Reply)
        .join(Reply.comment)
        .join(Comment.post)
        .options(contains_eager(Reply.comment).contains_eager(Comment.post))
        .where(Reply.status == status_upper)
    )
    if subreddit:
        normalized = subreddit.strip().removeprefix("r/").lower()
        stmt = stmt.where(Post.subreddit.ilike(normalized))
    if platform:
        stmt = stmt.where(Reply.platform == platform)

    if order == "newest":
        # Used by the Live board so smaller subreddits aren't drowned out by
        # high-upvote floods (e.g. r/technology) in the top N.
        if status_upper == "POSTED":
            stmt = stmt.order_by(
                nullslast(Reply.posted_at.desc()),
                Reply.created_at.desc(),
            ).limit(limit)
        else:
            stmt = stmt.order_by(Reply.created_at.desc()).limit(limit)
    else:
        stmt = stmt.order_by(
            Post.upvotes.desc(),
            Comment.upvotes.desc(),
            Post.number_of_comments.desc(),
            Reply.created_at.desc(),
        ).limit(limit)
    replies = list(db.scalars(stmt).all())

    # Promo floor: when min_promo > 0, ensure the returned set contains at
    # least that many promo replies. If the natural top-N falls short, top
    # up from the rest of the pool with the newest promos, replacing the
    # oldest normals so the window stays bounded at `limit`.
    if min_promo > 0 and replies:
        current_promo = sum(1 for r in replies if r.includes_promo)
        shortfall = min_promo - current_promo
        if shortfall > 0:
            seen_ids = {r.id for r in replies}
            backfill_stmt = (
                select(Reply)
                .join(Reply.comment)
                .join(Comment.post)
                .options(contains_eager(Reply.comment).contains_eager(Comment.post))
                .where(Reply.status == status_upper, Reply.includes_promo == True)  # noqa: E712
                .where(~Reply.id.in_(seen_ids))
            )
            if subreddit:
                normalized = subreddit.strip().removeprefix("r/").lower()
                backfill_stmt = backfill_stmt.where(Post.subreddit.ilike(normalized))
            backfill_stmt = backfill_stmt.order_by(Reply.created_at.desc()).limit(shortfall)
            extras = list(db.scalars(backfill_stmt).all())
            if extras:
                # Drop the oldest normals to make room; keep all existing promos.
                normals = [r for r in replies if not r.includes_promo]
                promos = [r for r in replies if r.includes_promo]
                # Sort normals oldest-first so we discard them first.
                normals.sort(key=lambda r: r.created_at or datetime.min)
                drop_n = min(len(extras), len(normals))
                kept_normals = normals[drop_n:]
                replies = promos + kept_normals + extras
                # Restore newest-first ordering.
                replies.sort(key=lambda r: r.created_at or datetime.min, reverse=True)

    items = []
    for reply in replies:
        comment = reply.comment
        post = comment.post
        items.append(
            ReplyItem(
                reply_id=reply.id,
                reply_text=reply.reply_text,
                is_ai_relevant=reply.is_ai_relevant,
                includes_promo=reply.includes_promo,
                status=reply.status,
                created_at=reply.created_at,
                comment_text=comment.text,
                comment_url=comment.comment_url,
                comment_author=comment.author,
                comment_upvotes=comment.upvotes,
                post_id=post.id,
                post_title=post.title,
                post_body=post.body,
                post_url=post.url,
                post_upvotes=post.upvotes,
                post_comment_count=post.number_of_comments,
                subreddit=post.subreddit,
                target_type=reply.target_type,
                target_url=reply.target_url,
                reddit_post_id=reply.reddit_post_id,
                reddit_comment_id=reply.reddit_comment_id,
                posting_attempts=reply.posting_attempts or 0,
                posting_claimed_at=reply.posting_claimed_at,
                posting_claimed_by=reply.posting_claimed_by,
                posting_error=reply.posting_error,
                posted_at=reply.posted_at,
                posted_reddit_comment_id=reply.posted_reddit_comment_id,
                posted_url=reply.posted_url,
                platform=reply.platform or "reddit",
                platform_post_id=reply.platform_post_id,
                platform_comment_id=reply.platform_comment_id,
                platform_section=reply.platform_section,
                posted_platform_comment_id=reply.posted_platform_comment_id,
            )
        )
    return items


@router.get("/summary", response_model=list[ReplySummaryItem])
def get_replies_summary(
    status: str = Query(default="POSTED"),
    subreddit: str | None = Query(default=None),
    platform: str | None = Query(default=None, pattern=r"^(reddit|glp|chan)$"),
    limit: int = Query(default=2000, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    """Lightweight feed/analytics projection.

    The dashboard's Posted analytics and recently-posted feed read only a
    handful of fields, all of which live on the Reply row. Selecting just
    those columns (no comment/post JOIN, no heavy post_body/comment_text)
    turns a ~5 MiB response into a ~0.5 MiB one and keeps the query single-
    table. Ordering mirrors the main endpoint's POSTED ordering.
    """
    status_upper = status.upper()
    stmt = select(
        Reply.id,
        Reply.reply_text,
        Reply.includes_promo,
        Reply.status,
        Reply.created_at,
        Reply.subreddit,
        Reply.posted_at,
        Reply.posted_url,
        Reply.platform,
        Reply.platform_section,
    ).where(Reply.status == status_upper)
    if platform:
        stmt = stmt.where(Reply.platform == platform)
    if subreddit:
        normalized = subreddit.strip().removeprefix("r/").lower()
        stmt = stmt.where(Reply.subreddit.ilike(normalized))
    stmt = stmt.order_by(
        nullslast(Reply.posted_at.desc()),
        Reply.created_at.desc(),
    ).limit(limit)

    return [
        ReplySummaryItem(
            reply_id=row.id,
            reply_text=row.reply_text,
            includes_promo=row.includes_promo,
            status=row.status,
            created_at=row.created_at,
            subreddit=row.subreddit,
            posted_at=row.posted_at,
            posted_url=row.posted_url,
            platform=row.platform or "reddit",
            platform_section=row.platform_section,
        )
        for row in db.execute(stmt).all()
    ]


@router.patch("/bulk/status")
def bulk_update_reply_status(
    payload: ReplyBulkUpdate,
    db: Session = Depends(get_db),
):
    if payload.status is None:
        raise HTTPException(status_code=400, detail="status is required")

    replies = db.scalars(select(Reply).where(Reply.id.in_(payload.reply_ids))).all()
    if not replies:
        raise HTTPException(status_code=404, detail="No replies found")

    status = payload.status.upper()
    for reply in replies:
        reply.status = status
        db.add(reply)
    db.commit()
    return {"message": "Replies updated", "updated": len(replies), "status": status}


@router.post("/regenerate")
def regenerate_replies(
    status: str = Query(default="PENDING"),
    limit: int = Query(default=200, ge=1, le=1000),
    reroll_promo: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    """Re-run the LLM on all replies in a given status, with the current prompt
    + post-processor. Useful after a prompt change to refresh stale drafts.

    - status: which bucket to refresh (default PENDING).
    - reroll_promo: if True, re-randomizes whether each reply includes a promo
      (per the current PROMO_RATIO). If False, preserves the existing flag.
    """
    stmt = (
        select(Reply)
        .join(Reply.comment)
        .where(Reply.status == status.upper())
        .order_by(Reply.id.asc())
        .limit(limit)
    )
    replies = db.scalars(stmt).all()

    refreshed = 0
    failed: list[dict] = []
    for reply in replies:
        comment = reply.comment
        if not comment or not comment.text:
            failed.append({"reply_id": reply.id, "error": "missing comment text"})
            continue
        include_promo = should_insert_promo() if reroll_promo else bool(reply.includes_promo)
        try:
            new_text = generate_reply(comment.text, include_promo)
        except Exception as exc:  # noqa: BLE001
            failed.append({"reply_id": reply.id, "error": str(exc)[:200]})
            continue
        if not new_text:
            failed.append({"reply_id": reply.id, "error": "LLM returned empty text"})
            continue
        reply.reply_text = new_text
        reply.includes_promo = include_promo
        db.add(reply)
        refreshed += 1
    db.commit()
    return {
        "scanned": len(replies),
        "refreshed": refreshed,
        "failed_count": len(failed),
        "failed_sample": failed[:5],
    }


@router.post("/generate-from-existing")
def generate_replies_from_existing(
    payload: GenerateRepliesFromExistingRequest,
    db: Session = Depends(get_db),
):
    """Queue Celery jobs that run the LLM on already-scraped comments without
    a Reply yet, one job per subreddit. No Apify involvement."""
    from worker.tasks import generate_replies_from_existing_job  # local to avoid import cycle on app start

    if payload.subreddits:
        names = [s.strip().removeprefix("r/").strip() for s in payload.subreddits if s and s.strip()]
    else:
        rows = db.scalars(select(TrackedSubreddit.name)).all()
        names = list(rows)

    if not names:
        raise HTTPException(status_code=400, detail="No subreddits to process")

    jobs = []
    cutoff_iso = (
        payload.max_comment_created_at.isoformat()
        if payload.max_comment_created_at is not None
        else None
    )
    for name in names:
        task = generate_replies_from_existing_job.delay(
            subreddit=name,
            limit=payload.per_sub_limit,
            max_comment_created_at=cutoff_iso,
            promo_ratio_override=payload.promo_ratio_override,
            skip_judge=payload.skip_judge,
        )
        jobs.append({"subreddit": name, "task_id": task.id})
    return {
        "queued": len(jobs),
        "per_sub_limit": payload.per_sub_limit,
        "max_comment_created_at": cutoff_iso,
        "promo_ratio_override": payload.promo_ratio_override,
        "skip_judge": payload.skip_judge,
        "jobs": jobs,
    }


@router.post("/{reply_id}/mark-posted")
def mark_reply_posted_by_account(
    reply_id: int,
    payload: ReplyMarkPostedByAccount,
    db: Session = Depends(get_db),
):
    """Operator manually posted this reply using the given account.

    Sets reply.status=POSTED, posted_at=now, posting_account_id=account_id, and
    applies the per-account cooldown (`next_eligible_at`) so the rest of the
    rate-limiting machinery treats it identically to a worker post."""
    reply = db.get(Reply, reply_id)
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")
    if reply.status == "POSTED":
        return {
            "reply_id": reply.id,
            "status": reply.status,
            "posted_at": reply.posted_at,
            "posted_url": reply.posted_url,
        }

    account = db.get(RedditAccount, payload.account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    if payload.reply_text is not None:
        text = payload.reply_text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="reply_text cannot be blank")
        reply.reply_text = text

    now = datetime.utcnow()
    reply.status = "POSTED"
    reply.posted_at = now
    reply.posting_account_id = account.id
    reply.posted_url = payload.posted_url.strip()
    reply.posting_error = None
    db.add(reply)

    # Free-burst rule: an account can fire 3 posts back-to-back without a
    # cooldown between them; the 3rd post in the burst applies the normal
    # 3-min jitter. "Back-to-back" = within FREE_BURST_WINDOW_MIN of each other.
    FREE_BURST_WINDOW_MIN = 10
    FREE_BURST_SIZE = 3
    previous_posts_in_free_burst = db.scalar(
        select(func.count(Reply.id)).where(
            Reply.posting_account_id == account.id,
            Reply.posted_at != None,  # noqa: E711
            Reply.posted_at >= now - timedelta(minutes=FREE_BURST_WINDOW_MIN),
        )
    ) or 0
    posts_in_free_burst = previous_posts_in_free_burst + 1

    if posts_in_free_burst < FREE_BURST_SIZE:
        # 1st or 2nd post in the current 10-min burst — no cooldown.
        cooldown_seconds = 0
    else:
        min_s = account.min_seconds_between_posts or 180
        max_s = max(min_s, account.max_seconds_between_posts or min_s)
        cooldown_seconds = random.uniform(min_s, max_s)
    if cooldown_seconds > 0:
        account.next_eligible_at = now + timedelta(seconds=cooldown_seconds)
    else:
        account.next_eligible_at = None
    db.add(account)

    db.commit()
    db.refresh(reply)
    return {
        "reply_id": reply.id,
        "status": reply.status,
        "posted_at": reply.posted_at,
        "posted_url": reply.posted_url,
        "next_eligible_at": account.next_eligible_at,
    }


@router.patch("/{reply_id}")
def update_reply_status(
    reply_id: int,
    payload: ReplyStatusUpdate,
    db: Session = Depends(get_db),
):
    reply = db.get(Reply, reply_id)
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")

    if payload.status is None and payload.reply_text is None:
        raise HTTPException(status_code=400, detail="status or reply_text is required")

    if payload.status is not None:
        reply.status = payload.status.upper()
    if payload.reply_text is not None:
        reply_text = payload.reply_text.strip()
        if not reply_text:
            raise HTTPException(status_code=400, detail="reply_text cannot be blank")
        reply.reply_text = reply_text
    db.add(reply)
    db.commit()
    db.refresh(reply)
    return {"message": "Reply updated", "reply_id": reply.id, "status": reply.status}
