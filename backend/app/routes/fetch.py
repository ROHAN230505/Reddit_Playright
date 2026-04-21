from fastapi import APIRouter

from app.schemas import FetchRequest
from worker.tasks import process_subreddit_job

router = APIRouter(prefix="/fetch", tags=["fetch"])


@router.post("")
def trigger_fetch(payload: FetchRequest):
    queued = []
    for subreddit in payload.subreddits:
        normalized_name = subreddit.strip().removeprefix("r/")
        if not normalized_name:
            continue
        task = process_subreddit_job.delay(
            subreddit=normalized_name,
            limit=payload.limit,
            source="manual_selected",
            triggered_by="api:/fetch",
        )
        queued.append({"subreddit": normalized_name, "task_id": task.id})

    return {"message": "Fetch jobs queued", "jobs": queued}
