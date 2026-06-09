from datetime import datetime

from app.db.session import SessionLocal
from app.db.models import ScrapeRun, TrackedSubreddit
from app.services.processor import (
    ensure_default_tracked_subreddits,
    generate_replies_for_unreplied,
    process_chan,
    process_glp,
    process_subreddit,
)
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


@celery.task(name="generate_replies_from_existing_job")
def generate_replies_from_existing_job(
    subreddit: str,
    limit: int = 30,
    max_comment_created_at: str | None = None,
    promo_ratio_override: float | None = None,
    skip_judge: bool = False,
):
    """Run the LLM on already-scraped comments without a Reply, for one
    subreddit. No Apify call — useful when the scrape pipeline is blocked.

    - max_comment_created_at: ISO datetime; only consider comments older than this.
    - promo_ratio_override: override REPLY_PROMO_RATIO for this batch (e.g. 0.8).
    - skip_judge: bypass the promo-naturalness judge (force promo through)."""
    from datetime import datetime as _dt

    db = SessionLocal()
    try:
        cutoff = _dt.fromisoformat(max_comment_created_at) if max_comment_created_at else None
        return generate_replies_for_unreplied(
            db,
            subreddit=subreddit,
            limit=limit,
            max_comment_created_at=cutoff,
            promo_ratio_override=promo_ratio_override,
            skip_judge=skip_judge,
        )
    finally:
        db.close()


@celery.task(name="process_glp_job")
def process_glp_job(limit: int = 30, source: str = "manual_api",
                    triggered_by: str | None = None):
    """Scrape GLP newthreads, classify each thread's posts, draft replies.

    Mirrors `process_subreddit_job` but for godlikeproductions.com — uses the
    glp_service Playwright fetcher instead of Apify, and tags every generated
    Reply with platform='glp' so the posting worker routes correctly."""
    db = SessionLocal()
    try:
        scrape_run = ScrapeRun(
            subreddit="glp",
            source=source,
            limit=limit,
            status="RUNNING",
            triggered_by=triggered_by,
        )
        db.add(scrape_run)
        db.commit()
        db.refresh(scrape_run)
        try:
            result = process_glp(db, limit=limit, scrape_run=scrape_run)
            scrape_run.status = "SUCCEEDED"
            scrape_run.posts_count = result["posts"]
            scrape_run.comments_count = result["comments"]
            scrape_run.replies_count = result["replies"]
            scrape_run.finished_at = datetime.utcnow()
            db.add(scrape_run)
            db.commit()
            return result
        except Exception as exc:
            scrape_run.status = "FAILED"
            scrape_run.error_message = str(exc)[:4000]
            scrape_run.finished_at = datetime.utcnow()
            db.add(scrape_run)
            db.commit()
            raise
    finally:
        db.close()


@celery.task(name="process_chan_job")
def process_chan_job(
    boards: list[str] | None = None,
    threads_per_board: int | None = None,
    source: str = "manual_api",
    triggered_by: str | None = None,
):
    """Scrape 4chan board catalogs + threads, classify, draft replies.

    Mirrors `process_glp_job` but reads from the 4chan JSON API (no Playwright).
    Tags every reply with platform='chan'."""
    db = SessionLocal()
    try:
        scrape_run = ScrapeRun(
            subreddit="chan",
            source=source,
            limit=threads_per_board or 0,
            status="RUNNING",
            triggered_by=triggered_by,
        )
        db.add(scrape_run)
        db.commit()
        db.refresh(scrape_run)
        try:
            result = process_chan(
                db,
                boards=boards,
                threads_per_board=threads_per_board,
                scrape_run=scrape_run,
            )
            scrape_run.status = "SUCCEEDED"
            scrape_run.posts_count = result["posts"]
            scrape_run.comments_count = result["comments"]
            scrape_run.replies_count = result["replies"]
            scrape_run.finished_at = datetime.utcnow()
            db.add(scrape_run)
            db.commit()
            return result
        except Exception as exc:
            scrape_run.status = "FAILED"
            scrape_run.error_message = str(exc)[:4000]
            scrape_run.finished_at = datetime.utcnow()
            db.add(scrape_run)
            db.commit()
            raise
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
