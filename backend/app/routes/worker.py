from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Reply
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
    )


@router.post("/claim", response_model=WorkerJobItem | None)
def claim_next(payload: WorkerClaimRequest, db: Session = Depends(get_db)):
    """Atomically claim the next APPROVED reply for posting, or recover a
    stale POSTING claim that has exceeded ``stale_after_seconds``. Returns
    null when no work is available."""
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=payload.stale_after_seconds)

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
        .limit(1)
    )

    dialect = db.bind.dialect.name if db.bind is not None else ""
    if dialect == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    reply = db.scalar(stmt)
    if not reply:
        return None

    target_url, subreddit, target_type = _resolve_target(reply)
    if not target_url:
        # Don't mark as POSTING for unworkable rows — fail it instead so the
        # operator sees the issue in the dashboard rather than thrash on it.
        reply.status = STATUS_FAILED
        reply.posting_error = "Reply has no resolvable Reddit target URL"
        reply.posting_claimed_at = None
        reply.posting_claimed_by = None
        db.add(reply)
        db.commit()
        return None

    reply.status = STATUS_POSTING
    reply.posting_claimed_at = now
    reply.posting_claimed_by = payload.worker_name
    reply.posting_attempts = (reply.posting_attempts or 0) + 1
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

    reply.status = STATUS_POSTED
    reply.posted_at = datetime.utcnow()
    reply.posting_error = None
    if payload.posted_reddit_comment_id:
        reply.posted_reddit_comment_id = payload.posted_reddit_comment_id
    db.add(reply)
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
