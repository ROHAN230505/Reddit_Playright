from app.db.session import SessionLocal
from app.db.models import TrackedSubreddit
from app.services.processor import ensure_default_tracked_subreddits, process_subreddit
from worker.celery_app import celery


@celery.task(name="process_subreddit_job")
def process_subreddit_job(subreddit: str, limit: int = 50):
    db = SessionLocal()
    try:
        return process_subreddit(db, subreddit=subreddit, limit=limit)
    finally:
        db.close()


@celery.task(name="process_tracked_subreddits_job")
def process_tracked_subreddits_job(limit: int = 15):
    db = SessionLocal()
    try:
        ensure_default_tracked_subreddits(db)
        subreddits = db.query(TrackedSubreddit).order_by(TrackedSubreddit.name.asc()).all()
        results = []
        for item in subreddits:
            results.append(
                {
                    "subreddit": item.name,
                    "result": process_subreddit(db, subreddit=item.name, limit=limit),
                }
            )
        return results
    finally:
        db.close()
