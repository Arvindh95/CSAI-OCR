import os
from uuid import UUID

from redis import Redis
from rq import Queue

QUEUE_NAME = "csai-ocr"
_REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")


def get_queue(redis: Redis | None = None) -> Queue:
    r = redis or Redis.from_url(_REDIS_URL)
    return Queue(QUEUE_NAME, connection=r)


def enqueue_ocr_job(
    job_id: UUID,
    endpoint: str,
    storage_path: str,
    client_id: int,
    period_id: int,
    template_id: int | None = None,
    redis: Redis | None = None,
) -> None:
    q = get_queue(redis)
    q.enqueue(
        "app.worker.run_ocr_job",
        str(job_id),
        endpoint,
        storage_path,
        client_id,
        period_id,
        template_id,
        job_id=str(job_id),
        result_ttl=3600,
        failure_ttl=86400,
        job_timeout=600,
        on_failure="app.worker.on_ocr_failure",
    )
