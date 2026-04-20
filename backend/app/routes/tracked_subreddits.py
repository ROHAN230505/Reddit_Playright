from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import TrackedSubreddit
from app.db.session import get_db
from app.schemas import TrackedSubredditCreate, TrackedSubredditItem
from app.services.processor import ensure_default_tracked_subreddits
from worker.tasks import process_subreddit_job

router = APIRouter(prefix="/tracked-subreddits", tags=["tracked-subreddits"])


@router.get("", response_model=list[TrackedSubredditItem])
def list_tracked_subreddits(db: Session = Depends(get_db)):
    ensure_default_tracked_subreddits(db)
    stmt = select(TrackedSubreddit).order_by(TrackedSubreddit.name.asc())
    return db.scalars(stmt).all()


@router.post("", response_model=TrackedSubredditItem)
def create_tracked_subreddit(
    payload: TrackedSubredditCreate,
    db: Session = Depends(get_db),
):
    ensure_default_tracked_subreddits(db)
    name = payload.name.strip().removeprefix("r/").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Subreddit name is required")

    existing = db.scalar(
        select(TrackedSubreddit).where(func.lower(TrackedSubreddit.name) == name.lower())
    )
    if existing:
        return existing

    item = TrackedSubreddit(name=name)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{subreddit_id}")
def delete_tracked_subreddit(subreddit_id: int, db: Session = Depends(get_db)):
    item = db.get(TrackedSubreddit, subreddit_id)
    if not item:
        raise HTTPException(status_code=404, detail="Tracked subreddit not found")

    db.delete(item)
    db.commit()
    return {"message": "Tracked subreddit removed", "id": subreddit_id}


@router.post("/run")
def run_tracked_subreddits(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    ensure_default_tracked_subreddits(db)
    subreddits = db.scalars(
        select(TrackedSubreddit).order_by(TrackedSubreddit.name.asc())
    ).all()
    jobs = []
    for item in subreddits:
        task = process_subreddit_job.delay(subreddit=item.name, limit=limit)
        jobs.append({"subreddit": item.name, "task_id": task.id})
    return {"message": "Tracked subreddit jobs queued", "jobs": jobs}
