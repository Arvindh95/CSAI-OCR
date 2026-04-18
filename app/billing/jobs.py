from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.models import Job


async def create_job(
    session: AsyncSession,
    client_id: int,
    period_id: int,
    endpoint: str,
    pages: int = 1,
    idempotency_key: str | None = None,
    body_hash: bytes | None = None,
    input_meta: dict | None = None,
    ip_address: str | None = None,
) -> Job:
    job = Job(
        id=uuid4(),
        client_id=client_id,
        period_id=period_id,
        endpoint=endpoint,
        status="queued",
        pages_submitted=pages,
        attempts=0,
        idempotency_key=idempotency_key,
        body_hash=body_hash,
        input_meta=input_meta,
        queued_at=datetime.now(timezone.utc),
        ip_address=ip_address,
    )
    session.add(job)
    await session.flush()
    return job


async def get_job(session: AsyncSession, client_id: int, job_id: UUID) -> Job | None:
    result = await session.execute(
        select(Job).where(Job.id == job_id, Job.client_id == client_id)
    )
    return result.scalar_one_or_none()


async def mark_started(session: AsyncSession, job_id: UUID) -> None:
    await session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(status="running", started_at=datetime.now(timezone.utc), attempts=Job.attempts + 1)
    )


async def mark_done(session: AsyncSession, job_id: UUID, result: dict) -> None:
    await session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(status="done", result=result, completed_at=datetime.now(timezone.utc))
    )


async def mark_failed(session: AsyncSession, job_id: UUID, error_msg: str) -> None:
    await session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(status="failed", error_msg=error_msg, completed_at=datetime.now(timezone.utc))
    )
