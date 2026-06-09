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
    },
    # GLP volume is high but moderation is aggressive — every 15 min keeps the
    # queue full without making us look like a crawler. Skip if GLP_ENABLED
    # is unset (so existing Reddit-only deployments don't try to scrape GLP).
    "glp-scrape-every-15-min": {
        "task": "process_glp_job",
        "schedule": crontab(minute="*/15"),
        "args": (30, "scheduler", "celery-beat-glp-15m-scrape"),
    },
}

# 4chan threads cycle fast (catalogs turn over in hours, not days). A 15min
# cadence with CHAN_THREADS_PER_BOARD=2 keeps the freshly-drafted queue sized to
# the ~20/hr posting cap — generating more just rots, since threads archive
# within hours. Stays well under 4chan's ≤1 req/sec limit (~6 requests/tick: 2
# catalogs + ≤4 threads). Gated by CHAN_SCRAPE_ENABLED so generation can be
# stopped without touching posting.
if settings.chan_scrape_enabled:
    celery.conf.beat_schedule["chan-scrape-every-15-min"] = {
        "task": "process_chan_job",
        "schedule": crontab(minute="*/15"),
        "args": (None, None, "scheduler", "celery-beat-chan-15m-scrape"),
    }

# Ensure task modules are loaded so both the worker and beat can register jobs.
import worker.tasks  # noqa: E402,F401
