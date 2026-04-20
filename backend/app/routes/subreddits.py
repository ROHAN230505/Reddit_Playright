from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Comment, Post
from app.db.session import get_db
from app.schemas import ContentCommentItem, ContentPostItem, SubredditContentResponse

router = APIRouter(prefix="/subreddits", tags=["subreddits"])


@router.get("/{subreddit}/content", response_model=SubredditContentResponse)
def get_subreddit_content(
    subreddit: str,
    post_limit: int = Query(default=12, ge=1, le=50),
    comment_limit: int = Query(default=6, ge=1, le=20),
    db: Session = Depends(get_db),
):
    normalized = subreddit.strip().removeprefix("r/")
    post_stmt = (
        select(Post)
        .where(func.lower(Post.subreddit) == normalized.lower())
        .order_by(Post.upvotes.desc(), Post.created_at.desc())
        .limit(post_limit)
    )
    posts = db.scalars(post_stmt).all()

    comment_count = db.scalar(
        select(func.count(Comment.id))
        .join(Post, Comment.post_id == Post.id)
        .where(func.lower(Post.subreddit) == normalized.lower())
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
        post_count=len(posts),
        comment_count=comment_count,
        posts=items,
    )
