from celery import Celery
from celery.schedules import crontab
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "disaster_alert",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.scheduler"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Manila",
    enable_utc=True,
    task_always_eager=False,
    broker_connection_retry_on_startup=True,
)

celery_app.conf.beat_schedule = {
    "poll-external-sources": {
        "task": "app.tasks.scheduler.poll_external_sources",
        "schedule": crontab(minute=f"*/{settings.POLLING_INTERVAL_MINUTES}"),
        "options": {"expires": 600},
    },
    "process-pending-articles": {
        "task": "app.tasks.scheduler.process_pending_articles",
        "schedule": crontab(minute="*/15"),
        "options": {"expires": 900},
    },
    "publish-approved-posts": {
        "task": "app.tasks.scheduler.publish_approved_posts",
        "schedule": crontab(minute="*/30"),
        "options": {"expires": 300},
    },
    "retry-failed-posts": {
        "task": "app.tasks.scheduler.retry_failed_posts",
        "schedule": crontab(minute="*/10"),
        "options": {"expires": 300},
    },
}

celery_app.autodiscover_tasks([])