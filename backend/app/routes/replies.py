from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Reply
from app.db.session import get_db
from app.schemas import ReplyItem, ReplyStatusUpdate

router = APIRouter(prefix="/replies", tags=["replies"])


@router.get("", response_model=list[ReplyItem])
def get_replies(
    status: str = Query(default="PENDING"),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Reply)
        .where(Reply.status == status)
        .order_by(Reply.created_at.desc())
    )
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
                post_id=post.id,
                post_title=post.title,
                post_url=post.url,
                subreddit=post.subreddit,
            )
        )
    return items


@router.patch("/{reply_id}")
def update_reply_status(
    reply_id: int,
    payload: ReplyStatusUpdate,
    db: Session = Depends(get_db),
):
    reply = db.get(Reply, reply_id)
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")

    reply.status = payload.status.upper()
    db.add(reply)
    db.commit()
    db.refresh(reply)
    return {"message": "Reply updated", "reply_id": reply.id, "status": reply.status}
