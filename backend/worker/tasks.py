from app.db.session import SessionLocal
from app.services.processor import process_subreddit
from worker.celery_app import celery


@celery.task(name="process_subreddit_job")
def process_subreddit_job(subreddit: str, limit: int = 50):
    db = SessionLocal()
    try:
        return process_subreddit(db, subreddit=subreddit, limit=limit)
    finally:
        db.close()
