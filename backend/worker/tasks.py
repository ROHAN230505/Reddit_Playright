from datetime import datetime

from app.db.session import SessionLocal
from app.db.models import ScrapeRun, TrackedSubreddit
from app.services.processor import ensure_default_tracked_subreddits, process_subreddit
from worker.celery_app import celery


@celery.task(name="process_subreddit_job")
def process_subreddit_job(
    subreddit: str,
    limit: int = 50,
    source: str = "manual_api",
    triggered_by: str | None = None,
):
    db = SessionLocal()
    try:
        return _run_subreddit_scrape(
            db,
            subreddit=subreddit,
            limit=limit,
            source=source,
            triggered_by=triggered_by,
        )
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
                    "result": _run_subreddit_scrape(
                        db,
                        subreddit=item.name,
                        limit=limit,
                        source="scheduler",
                        triggered_by="celery-beat-six-hour-tracked-subreddit-scrape",
                    ),
                }
            )
        return results
    finally:
        db.close()


def _run_subreddit_scrape(
    db,
    subreddit: str,
    limit: int,
    source: str,
    triggered_by: str | None,
):
    normalized = subreddit.strip().removeprefix("r/")
    scrape_run = ScrapeRun(
        subreddit=normalized,
        source=source,
        limit=limit,
        status="RUNNING",
        triggered_by=triggered_by,
    )
    db.add(scrape_run)
    db.commit()
    db.refresh(scrape_run)

    try:
        result = process_subreddit(
            db,
            subreddit=normalized,
            limit=limit,
            scrape_run=scrape_run,
        )
        scrape_run.status = "SUCCEEDED"
        scrape_run.posts_count = result["posts"]
        scrape_run.comments_count = result["comments"]
        scrape_run.replies_count = result["replies"]
        scrape_run.apify_run_id = result.get("apify_run_id")
        scrape_run.finished_at = datetime.utcnow()
        db.add(scrape_run)
        db.commit()
        return result
    except Exception as exc:
        scrape_run.status = "FAILED"
        scrape_run.error_message = str(exc)
        scrape_run.finished_at = datetime.utcnow()
        db.add(scrape_run)
        db.commit()
        raise
