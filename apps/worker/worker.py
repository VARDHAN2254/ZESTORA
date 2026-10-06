import os

from celery import Celery

broker_url = os.getenv("CELERY_BROKER_URL", "memory://")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "cache+memory://")

celery = Celery(
    "zestora_worker",
    broker=broker_url,
    backend=result_backend,
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)


@celery.task(name="worker.ping")
def ping() -> str:
    """Minimal task used for worker liveness verification."""
    return "pong"
