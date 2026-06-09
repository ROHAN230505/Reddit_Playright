import random
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Comment, RedditAccount, Reply
from app.db.session import get_db
from app.schemas import (
    WorkerClaimRequest,
    WorkerJobItem,
    WorkerMarkFailedRequest,
    WorkerMarkPostedRequest,
)

router = APIRouter(prefix="/worker", tags=["worker"])


# Status values used by the Playwright posting worker. Existing values
# (PENDING, DONE) remain valid; these are additive.
STATUS_APPROVED = "APPROVED"
STATUS_POSTING = "POSTING"
STATUS_POSTED = "POSTED"
STATUS_FAILED = "FAILED"


def _resolve_target(reply: Reply) -> tuple[str, str | None, str | None]:
    """Return (target_url, subreddit, target_type) using stored fields with
    a safe fallback to the linked Comment/Post when the reply was created
    before posting metadata existed."""
    target_url = reply.target_url
    subreddit = reply.subreddit
    target_type = reply.target_type

    if reply.comment is not None:
        comment = reply.comment
        post = comment.post
        if not target_url:
            target_url = comment.comment_url or (post.url if post else None)
        if not subreddit and post is not None:
            subreddit = post.subreddit
        if not target_type:
            target_type = "comment" if comment.comment_url else "post"

    return target_url or "", subreddit, target_type or "comment"


def _job_payload(reply: Reply) -> WorkerJobItem:
    target_url, subreddit, target_type = _resolve_target(reply)
    return WorkerJobItem(
        reply_id=reply.id,
        reply_text=reply.reply_text,
        target_type=target_type,
        target_url=target_url,
        subreddit=subreddit,
        reddit_post_id=reply.reddit_post_id,
        reddit_comment_id=reply.reddit_comment_id,
        status=reply.status,
        posting_attempts=reply.posting_attempts or 0,
        posting_claimed_at=reply.posting_claimed_at,
        posting_claimed_by=reply.posting_claimed_by,
        approved_at=None,
        created_at=reply.created_at,
        platform=reply.platform or "reddit",
        platform_post_id=reply.platform_post_id,
        platform_comment_id=reply.platform_comment_id,
        platform_section=reply.platform_section,
    )


def _account_rate_limited(
    db: Session, account: RedditAccount, now: datetime
) -> tuple[bool, str | None]:
    """Return (is_limited, reason) for the given account at `now`."""
    # Cooldown timer.
    if account.next_eligible_at and account.next_eligible_at > now:
        wait = int((account.next_eligible_at - now).total_seconds())
        return True, f"cooldown {wait}s remaining"

    # Hourly cap.
    hourly_cap = account.posts_per_hour_limit or 4
    posts_last_hour = db.scalar(
        select(func.count(Reply.id)).where(
            Reply.posting_account_id == account.id,
            Reply.posted_at != None,  # noqa: E711
            Reply.posted_at >= now - timedelta(hours=1),
        )
    ) or 0
    if posts_last_hour >= hourly_cap:
        return True, f"hourly limit reached ({posts_last_hour}/{hourly_cap})"

    # Daily cap.
    daily_cap = account.posts_per_day_limit or 30
    posts_last_day = db.scalar(
        select(func.count(Reply.id)).where(
            Reply.posting_account_id == account.id,
            Reply.posted_at != None,  # noqa: E711
            Reply.posted_at >= now - timedelta(days=1),
        )
    ) or 0
    if posts_last_day >= daily_cap:
        return True, f"daily limit reached ({posts_last_day}/{daily_cap})"

    return False, None


def _thread_at_cap(db: Session, reply: Reply, cap: int) -> bool:
    """True if the 4chan thread this reply targets already has `cap` or more
    replies POSTED or in-flight (POSTING). The thread is identified by the
    reply's comment's post_id (one Post per chan thread)."""
    comment = reply.comment
    if comment is None or comment.post_id is None:
        return False
    count = db.scalar(
        select(func.count(Reply.id))
        .join(Comment, Reply.comment_id == Comment.id)
        .where(
            Comment.post_id == comment.post_id,
            Reply.status.in_((STATUS_POSTED, STATUS_POSTING)),
        )
    ) or 0
    return count >= cap


@router.post("/claim", response_model=WorkerJobItem | None)
def claim_next(payload: WorkerClaimRequest, db: Session = Depends(get_db)):
    """Atomically claim the next APPROVED reply for posting, or recover a
    stale POSTING claim that has exceeded ``stale_after_seconds``. Returns
    null when no work is available OR when the requesting account is rate-
    limited (cooldown / hourly / daily caps)."""
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=payload.stale_after_seconds)

    # If a worker identifies its account, enforce per-account rate limits
    # BEFORE picking up work. Workers without account_id (legacy) bypass.
    account = None
    if payload.account_id is not None:
        account = db.get(RedditAccount, payload.account_id)
        if not account or not account.is_enabled:
            return None
        is_limited, _reason = _account_rate_limited(db, account, now)
        if is_limited:
            return None

    stmt = (
        select(Reply)
        .where(
            or_(
                Reply.status == STATUS_APPROVED,
                and_(
                    Reply.status == STATUS_POSTING,
                    Reply.posting_claimed_at != None,  # noqa: E711
                    Reply.posting_claimed_at < cutoff,
                ),
            )
        )
        .order_by(Reply.posting_attempts.asc(), Reply.id.asc())
    )
    # When the worker identifies its account, only hand out jobs for the
    # matching platform — a Reddit account can't post to GLP and vice versa.
    if account is not None:
        stmt = stmt.where(Reply.platform == (account.platform or "reddit"))
    # Explicit platform scope (e.g. a chan-only worker). Narrows further; never
    # widens past the account filter above.
    if payload.platform is not None:
        stmt = stmt.where(Reply.platform == payload.platform)

    # Per-thread cap (chan): skip candidates whose thread already has the max
    # number of POSTED/POSTING replies, so we spread across threads instead of
    # flooding one. We scan a bounded batch rather than limit(1) so a capped
    # thread doesn't starve the worker.
    effective_platform = payload.platform or (account.platform if account else None)
    per_thread_cap = (
        settings.chan_max_posts_per_thread if effective_platform == "chan" else 0
    )

    dialect = db.bind.dialect.name if db.bind is not None else ""
    if dialect == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    if per_thread_cap and per_thread_cap > 0:
        reply = None
        for candidate in db.scalars(stmt.limit(50)):
            if _thread_at_cap(db, candidate, per_thread_cap):
                continue
            reply = candidate
            break
    else:
        reply = db.scalar(stmt.limit(1))
    if not reply:
        return None

    target_url, subreddit, target_type = _resolve_target(reply)
    if not target_url:
        # Don't mark as POSTING for unworkable rows — fail it instead so the
        # operator sees the issue in the dashboard rather than thrash on it.
        reply.status = STATUS_FAILED
        reply.posting_error = "Reply has no resolvable target URL"
        reply.posting_claimed_at = None
        reply.posting_claimed_by = None
        db.add(reply)
        db.commit()
        return None

    reply.status = STATUS_POSTING
    reply.posting_claimed_at = now
    reply.posting_claimed_by = payload.worker_name
    reply.posting_attempts = (reply.posting_attempts or 0) + 1
    if payload.account_id is not None:
        reply.posting_account_id = payload.account_id
    if not reply.target_url:
        reply.target_url = target_url
    if not reply.subreddit:
        reply.subreddit = subreddit
    if not reply.target_type:
        reply.target_type = target_type
    db.add(reply)
    db.commit()
    db.refresh(reply)
    return _job_payload(reply)


@router.post("/{reply_id}/posted")
def mark_posted(
    reply_id: int,
    payload: WorkerMarkPostedRequest,
    db: Session = Depends(get_db),
):
    reply = db.get(Reply, reply_id)
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")

    # Idempotent — if already POSTED, return success without state change.
    if reply.status == STATUS_POSTED:
        return {
            "message": "Reply already marked posted",
            "reply_id": reply.id,
            "status": reply.status,
            "posted_at": reply.posted_at,
        }

    if reply.status != STATUS_POSTING:
        raise HTTPException(
            status_code=409,
            detail=f"Reply is not currently being posted (status={reply.status})",
        )

    if reply.posting_claimed_by and reply.posting_claimed_by != payload.worker_name:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Reply claimed by another worker "
                f"({reply.posting_claimed_by})"
            ),
        )

    now = datetime.utcnow()
    reply.status = STATUS_POSTED
    reply.posted_at = now
    reply.posting_error = None
    if payload.posted_reddit_comment_id:
        reply.posted_reddit_comment_id = payload.posted_reddit_comment_id
    if payload.posted_platform_comment_id:
        reply.posted_platform_comment_id = payload.posted_platform_comment_id
    if payload.posted_url:
        reply.posted_url = payload.posted_url
    db.add(reply)

    # Set the per-account cooldown so the next claim is throttled.
    if reply.posting_account_id is not None:
        account = db.get(RedditAccount, reply.posting_account_id)
        if account is not None:
            min_s = account.min_seconds_between_posts or 300
            max_s = max(min_s, account.max_seconds_between_posts or 900)
            jitter = random.uniform(min_s, max_s)
            account.next_eligible_at = now + timedelta(seconds=jitter)
            db.add(account)

    db.commit()
    db.refresh(reply)
    return {
        "message": "Reply marked posted",
        "reply_id": reply.id,
        "status": reply.status,
        "posted_at": reply.posted_at,
    }


@router.post("/{reply_id}/failed")
def mark_failed(
    reply_id: int,
    payload: WorkerMarkFailedRequest,
    db: Session = Depends(get_db),
):
    reply = db.get(Reply, reply_id)
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")

    if reply.status not in (STATUS_POSTING, STATUS_FAILED, STATUS_APPROVED):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot mark failed from status {reply.status}",
        )

    if (
        reply.status == STATUS_POSTING
        and reply.posting_claimed_by
        and reply.posting_claimed_by != payload.worker_name
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Reply claimed by another worker "
                f"({reply.posting_claimed_by})"
            ),
        )

    reply.posting_error = payload.error[:4000]
    reply.posting_claimed_at = None
    reply.posting_claimed_by = None
    if payload.requeue:
        reply.status = STATUS_APPROVED
    else:
        reply.status = STATUS_FAILED
    db.add(reply)
    db.commit()
    db.refresh(reply)
    return {
        "message": "Reply marked failed",
        "reply_id": reply.id,
        "status": reply.status,
        "posting_error": reply.posting_error,
    }


@router.get("/queue")
def queue_summary(db: Session = Depends(get_db)):
    """Lightweight visibility endpoint for dashboards/monitoring."""
    counts: dict[str, int] = {}
    for status in (STATUS_APPROVED, STATUS_POSTING, STATUS_POSTED, STATUS_FAILED):
        counts[status] = db.scalar(
            select(func.count(Reply.id)).where(Reply.status == status)
        ) or 0
    return {"counts": counts}
