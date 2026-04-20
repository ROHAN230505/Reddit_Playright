from fastapi import APIRouter

from app.schemas import FetchRequest
from worker.tasks import process_subreddit_job

router = APIRouter(prefix="/fetch", tags=["fetch"])


@router.post("")
def trigger_fetch(payload: FetchRequest):
    queued = []
    for subreddit in payload.subreddits:
        task = process_subreddit_job.delay(subreddit=subreddit, limit=payload.limit)
        queued.append({"subreddit": subreddit, "task_id": task.id})

    return {"message": "Fetch jobs queued", "jobs": queued}
