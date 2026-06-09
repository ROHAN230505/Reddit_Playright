"""4chan-specific operational endpoints (scrape trigger, config).

Generic reply CRUD lives in `replies.py` and accepts `?platform=chan`. This
router only holds actions that are intrinsically 4chan-shaped — i.e. ops that
don't fit the platform-neutral `/replies` or `/worker` namespaces.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.config import settings


router = APIRouter(prefix="/chan", tags=["chan"])


@router.post("/scrape-now")
def trigger_chan_scrape(threads_per_board: int | None = None):
    """Queue an immediate 4chan scrape Celery task (bypasses the 5-min beat).

    With CHAN_AUTO_APPROVE=1 (the default) every saved reply lands as
    APPROVED so the Playwright worker picks it up automatically."""
    from worker.tasks import process_chan_job  # local import to avoid cycle on app start

    task = process_chan_job.delay(None, threads_per_board, "manual_api", "dashboard")
    return {
        "task_id": task.id,
        "boards": settings.chan_boards,
        "threads_per_board": threads_per_board or settings.chan_threads_per_board,
        "auto_approve": settings.chan_auto_approve,
    }


@router.get("/config")
def get_chan_config():
    """Read-only view of 4chan-related backend config for the dashboard."""
    return {
        "auto_approve": settings.chan_auto_approve,
        "boards": settings.chan_boards,
        "threads_per_board": settings.chan_threads_per_board,
    }
