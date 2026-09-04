from celery import Celery

from app.config import settings
from app.observability import setup_logging


setup_logging()

celery_app = Celery(
    "recoverai",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.recovery",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue=settings.celery_task_default_queue,
    task_time_limit=30,
    task_soft_time_limit=20,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=5,
)
