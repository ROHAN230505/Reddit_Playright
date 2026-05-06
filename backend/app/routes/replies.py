from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Comment, Post, Reply
from app.db.session import get_db
from app.schemas import ReplyBulkUpdate, ReplyItem, ReplyStatusUpdate
from app.services.processor import generate_reply, should_insert_promo

router = APIRouter(prefix="/replies", tags=["replies"])


@router.get("", response_model=list[ReplyItem])
def get_replies(
    status: str = Query(default="PENDING"),
    subreddit: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(Reply).join(Reply.comment).join(Comment.post).where(Reply.status == status)
    if subreddit:
        normalized = subreddit.strip().removeprefix("r/").lower()
        stmt = stmt.where(Post.subreddit.ilike(normalized))

    stmt = stmt.order_by(
        Post.upvotes.desc(),
        Comment.upvotes.desc(),
        Post.number_of_comments.desc(),
        Reply.created_at.desc(),
    ).limit(limit)
    replies = db.scalars(stmt).all()

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
            )
        )
    return items


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
