from celery import Celery

from app.config import settings


celery = Celery("reddit_ai_worker", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.task_serializer = "json"
celery.conf.result_serializer = "json"
celery.conf.accept_content = ["json"]
