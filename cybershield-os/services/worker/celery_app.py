from celery import Celery
from app.config import settings

celery_app = Celery("cybershield", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_serializer="json", result_serializer="json", accept_content=["json"],
                       timezone="UTC", task_track_started=True, broker_connection_retry_on_startup=True)
celery_app.conf.beat_schedule = {
    "dispatch-webhook-outbox": {
        "task": "cybershield.dispatch_webhook_outbox",
        "schedule": 15.0,
    },
    "apply-event-retention": {
        "task": "cybershield.purge_expired_events",
        "schedule": 86400.0,
    },
    "record-daily-posture": {
        "task": "cybershield.record_posture_snapshots",
        "schedule": 86400.0,
    }
}
celery_app.autodiscover_tasks(["services.worker"])
