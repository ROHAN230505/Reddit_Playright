"""GLP-specific operational endpoints (scrape trigger, config knobs).

Generic reply CRUD lives in `replies.py` and accepts `?platform=glp`. This
router is only for actions that are intrinsically GLP-shaped — i.e. they
don't fit the platform-neutral `/replies` or `/worker` namespaces.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.config import settings


router = APIRouter(prefix="/glp", tags=["glp"])


@router.post("/scrape-now")
def trigger_glp_scrape(limit: int = 30):
    """Queue an immediate GLP scrape Celery task (bypasses the 15-min beat).

    Returns the task id so the caller can poll if needed. The task runs:
    fetch newthreads → fetch each thread → classify → draft replies. With
    GLP_AUTO_APPROVE=1 (the default) every saved reply lands as APPROVED so
    the Playwright worker picks it up automatically."""
    from worker.tasks import process_glp_job  # local import to avoid cycle on app start

    task = process_glp_job.delay(limit, "manual_api", "dashboard")
    return {
        "task_id": task.id,
        "limit": limit,
        "auto_approve": settings.glp_auto_approve,
    }


@router.get("/config")
def get_glp_config():
    """Read-only view of GLP-related backend config the dashboard can show
    to make it obvious whether auto-approve is on and which forum topics are
    being scraped."""
    return {
        "auto_approve": settings.glp_auto_approve,
        "topics": settings.glp_topics,
    }
