from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Comment, Post, Reply
from app.db.session import get_db
from app.schemas import (
    ContentCommentItem,
    ContentPostItem,
    OpportunityPostItem,
    OpportunityReplyItem,
    SubredditContentResponse,
    SubredditOpportunityResponse,
)

router = APIRouter(prefix="/subreddits", tags=["subreddits"])


@router.get("/{subreddit}/content", response_model=SubredditContentResponse)
def get_subreddit_content(
    subreddit: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=6, ge=1, le=24),
    comment_limit: int = Query(default=6, ge=1, le=20),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
):
    normalized = subreddit.strip().removeprefix("r/")
    filters = [func.lower(Post.subreddit) == normalized.lower()]
    if date_from is not None:
        filters.append(Post.created_at >= date_from)
    if date_to is not None:
        filters.append(Post.created_at <= date_to)

    total_posts = db.scalar(select(func.count(Post.id)).where(*filters)) or 0
    post_stmt = (
        select(Post)
        .where(*filters)
        .order_by(Post.upvotes.desc(), Post.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    posts = db.scalars(post_stmt).all()

    comment_count = db.scalar(
        select(func.count(Comment.id))
        .join(Post, Comment.post_id == Post.id)
        .where(*filters)
    ) or 0

    items = []
    for post in posts:
        comment_stmt = (
            select(Comment)
            .where(Comment.post_id == post.id)
            .order_by(Comment.upvotes.desc(), Comment.created_at.desc())
            .limit(comment_limit)
        )
        comments = db.scalars(comment_stmt).all()
        items.append(
            ContentPostItem(
                id=post.id,
                title=post.title,
                body=post.body,
                url=post.url,
                upvotes=post.upvotes,
                number_of_comments=post.number_of_comments,
                created_at=post.created_at,
                top_comments=[
                    ContentCommentItem(
                        id=comment.id,
                        text=comment.text,
                        author=comment.author,
                        comment_url=comment.comment_url,
                        upvotes=comment.upvotes,
                        created_at=comment.created_at,
                    )
                    for comment in comments
                ],
            )
        )

    return SubredditContentResponse(
        subreddit=normalized,
        page=page,
        page_size=page_size,
        total_posts=total_posts,
        post_count=len(posts),
        comment_count=comment_count,
        posts=items,
    )


@router.get("/{subreddit}/opportunities", response_model=SubredditOpportunityResponse)
def get_subreddit_opportunities(
    subreddit: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=4, ge=1, le=24),
    reply_limit: int = Query(default=3, ge=1, le=10),
    db: Session = Depends(get_db),
):
    normalized = subreddit.strip().removeprefix("r/")
    stmt = (
        select(Reply)
        .join(Reply.comment)
        .join(Comment.post)
        .where(
            Reply.status == "PENDING",
            func.lower(Post.subreddit) == normalized.lower(),
        )
        .order_by(
            Post.upvotes.desc(),
            Comment.upvotes.desc(),
            Post.number_of_comments.desc(),
            Reply.created_at.desc(),
        )
    )
    replies = db.scalars(stmt).all()

    grouped_posts: dict[int, dict] = {}
    for reply in replies:
        comment = reply.comment
        post = comment.post
        post_bucket = grouped_posts.setdefault(
            post.id,
            {
                "post_id": post.id,
                "subreddit": post.subreddit,
                "post_title": post.title,
                "post_body": post.body,
                "post_url": post.url,
                "post_upvotes": post.upvotes,
                "post_comment_count": post.number_of_comments,
                "post_created_at": post.created_at,
                "promotable_replies": [],
                "normal_replies": [],
                "opportunity_score": 0,
            },
        )
        value_score = max(post.upvotes, 0) * 3 + max(comment.upvotes, 0) * 4 + max(post.number_of_comments, 0)
        payload = OpportunityReplyItem(
            reply_id=reply.id,
            comment_text=comment.text,
            comment_url=comment.comment_url,
            comment_author=comment.author,
            comment_upvotes=comment.upvotes,
            reply_text=reply.reply_text,
            includes_promo=reply.includes_promo,
            created_at=reply.created_at,
            value_score=value_score,
        )
        bucket_name = "promotable_replies" if reply.includes_promo else "normal_replies"
        post_bucket[bucket_name].append(payload)
        post_bucket["opportunity_score"] += value_score

    grouped_items = []
    for item in grouped_posts.values():
        promotable = sorted(item["promotable_replies"], key=lambda candidate: candidate.value_score, reverse=True)
        normal = sorted(item["normal_replies"], key=lambda candidate: candidate.value_score, reverse=True)
        grouped_items.append(
            OpportunityPostItem(
                post_id=item["post_id"],
                subreddit=item["subreddit"],
                post_title=item["post_title"],
                post_body=item["post_body"],
                post_url=item["post_url"],
                post_upvotes=item["post_upvotes"],
                post_comment_count=item["post_comment_count"],
                post_created_at=item["post_created_at"],
                promotable_replies=promotable[:reply_limit],
                normal_replies=normal[:reply_limit],
                promotable_count=len(promotable),
                normal_count=len(normal),
                opportunity_score=item["opportunity_score"],
            )
        )

    grouped_items.sort(
        key=lambda item: (
            item.promotable_count + item.normal_count,
            item.opportunity_score,
            item.post_upvotes,
            item.post_comment_count,
        ),
        reverse=True,
    )
    total_posts = len(grouped_items)
    start = (page - 1) * page_size
    page_items = grouped_items[start : start + page_size]
    return SubredditOpportunityResponse(
        subreddit=normalized,
        page=page,
        page_size=page_size,
        total_posts=total_posts,
        posts=page_items,
    )
