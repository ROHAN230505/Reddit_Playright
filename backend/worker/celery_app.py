from celery import Celery
from celery.schedules import crontab

from app.config import settings


celery = Celery("reddit_ai_worker", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.task_serializer = "json"
celery.conf.result_serializer = "json"
celery.conf.accept_content = ["json"]
celery.conf.timezone = "UTC"
celery.conf.beat_schedule = {
    "six-hour-tracked-subreddit-scrape": {
        "task": "process_tracked_subreddits_job",
        "schedule": crontab(minute=0, hour="*/6"),
        "args": (settings.scrape_limit,),
    }
}

# Ensure task modules are loaded so both the worker and beat can register jobs.
import worker.tasks  # noqa: E402,F401
