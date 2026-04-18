from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.schemas import (
    ClientCreate,
    ClientCreated,
    ClientOut,
    ClientUpdate,
    JobOut,
    PlanOut,
    PlanUpsert,
    UsageOut,
)
from app.billing.auth import generate_api_key, hash_api_key, key_prefix
from app.billing.models import Client, Job, Plan
from app.billing.periods import current_plan, get_or_create_open_period
from app.billing.quota import current as quota_current, reset as quota_reset
from app.deps import get_redis_dep, get_session
from app.errors import BadRequest, NotFound

router = APIRouter(prefix="/admin/v1")


def _client_out(c: Client) -> dict:
    return {
        "id": c.id, "name": c.name, "email": c.email,
        "api_key_prefix": c.api_key_prefix, "is_active": c.is_active,
        "created_at": c.created_at,
    }


@router.post("/clients", response_model=ClientCreated, status_code=201)
async def create_client(body: ClientCreate, session: AsyncSession = Depends(get_session)):
    now = datetime.now(timezone.utc)
    raw_key = generate_api_key()
    client = Client(
        name=body.name, email=body.email,
        api_key_hash=hash_api_key(raw_key),
        api_key_prefix=key_prefix(raw_key),
        is_active=True, created_at=now,
    )
    session.add(client)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise BadRequest(f"email already in use: {body.email}")
    session.add(Plan(
        client_id=client.id,
        max_transactions=body.max_transactions,
        max_pages_per_txn=body.max_pages_per_txn,
        reset_period=body.reset_period,
        effective_from=now,
    ))
    await session.commit()
    return {**_client_out(client), "api_key": raw_key}


@router.get("/clients", response_model=list[ClientOut])
async def list_clients(
    active_only: bool = False,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Client).order_by(Client.id.desc())
    if active_only:
        stmt = stmt.where(Client.is_active.is_(True))
    result = await session.execute(stmt)
    return [_client_out(c) for c in result.scalars().all()]


@router.get("/clients/{client_id}", response_model=ClientOut)
async def get_client(client_id: int, session: AsyncSession = Depends(get_session)):
    c = await session.get(Client, client_id)
    if c is None:
        raise NotFound(f"client {client_id} not found")
    return _client_out(c)


@router.patch("/clients/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: int,
    body: ClientUpdate,
    session: AsyncSession = Depends(get_session),
):
    c = await session.get(Client, client_id)
    if c is None:
        raise NotFound(f"client {client_id} not found")
    if body.name is not None:
        c.name = body.name
    if body.email is not None:
        c.email = body.email
    if body.is_active is not None:
        c.is_active = body.is_active
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise BadRequest(f"email already in use: {body.email}")
    await session.refresh(c)
    return _client_out(c)


@router.post("/clients/{client_id}/rotate-key", response_model=ClientCreated)
async def rotate_key(client_id: int, session: AsyncSession = Depends(get_session)):
    c = await session.get(Client, client_id)
    if c is None:
        raise NotFound(f"client {client_id} not found")
    raw_key = generate_api_key()
    c.api_key_hash = hash_api_key(raw_key)
    c.api_key_prefix = key_prefix(raw_key)
    await session.commit()
    await session.refresh(c)
    return {**_client_out(c), "api_key": raw_key}


def _plan_out(p: Plan) -> dict:
    return {
        "max_transactions": p.max_transactions,
        "max_pages_per_txn": p.max_pages_per_txn,
        "reset_period": p.reset_period,
        "effective_from": p.effective_from,
        "effective_to": p.effective_to,
    }


@router.get("/clients/{client_id}/plan", response_model=PlanOut)
async def get_current_plan(client_id: int, session: AsyncSession = Depends(get_session)):
    c = await session.get(Client, client_id)
    if c is None:
        raise NotFound(f"client {client_id} not found")
    result = await session.execute(
        select(Plan).where(Plan.client_id == client_id, Plan.effective_to.is_(None))
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise NotFound(f"no active plan for client {client_id}")
    return _plan_out(plan)


@router.put("/clients/{client_id}/plan", response_model=PlanOut)
async def upsert_plan(
    client_id: int,
    body: PlanUpsert,
    session: AsyncSession = Depends(get_session),
):
    c = await session.get(Client, client_id)
    if c is None:
        raise NotFound(f"client {client_id} not found")
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(Plan).where(Plan.client_id == client_id, Plan.effective_to.is_(None))
    )
    old = result.scalar_one_or_none()
    if old is not None:
        old.effective_to = now
    new = Plan(
        client_id=client_id,
        max_transactions=body.max_transactions,
        max_pages_per_txn=body.max_pages_per_txn,
        reset_period=body.reset_period,
        effective_from=now,
    )
    session.add(new)
    await session.commit()
    await session.refresh(new)
    return _plan_out(new)


@router.delete("/clients/{client_id}", response_model=ClientOut)
async def deactivate_client(client_id: int, session: AsyncSession = Depends(get_session)):
    c = await session.get(Client, client_id)
    if c is None:
        raise NotFound(f"client {client_id} not found")
    c.is_active = False
    await session.commit()
    await session.refresh(c)
    return _client_out(c)


@router.get("/clients/{client_id}/usage", response_model=UsageOut)
async def get_usage(
    client_id: int,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis_dep),
):
    c = await session.get(Client, client_id)
    if c is None:
        raise NotFound(f"client {client_id} not found")
    plan = await current_plan(session, client_id)
    if plan is None:
        raise NotFound(f"no active plan for client {client_id}")
    period = await get_or_create_open_period(session, client_id)
    await session.commit()
    used = await quota_current(redis, client_id, period.id)
    limit = plan.max_transactions
    return {
        "period_id": period.id,
        "period_start": period.period_start,
        "period_end": period.period_end,
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
    }


@router.post("/clients/{client_id}/quota/reset", response_model=UsageOut)
async def reset_quota(
    client_id: int,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis_dep),
):
    c = await session.get(Client, client_id)
    if c is None:
        raise NotFound(f"client {client_id} not found")
    plan = await current_plan(session, client_id)
    if plan is None:
        raise NotFound(f"no active plan for client {client_id}")
    period = await get_or_create_open_period(session, client_id)
    await session.commit()
    await quota_reset(redis, client_id, period.id, 0)
    return {
        "period_id": period.id,
        "period_start": period.period_start,
        "period_end": period.period_end,
        "used": 0,
        "limit": plan.max_transactions,
        "remaining": plan.max_transactions,
    }


@router.get("/clients/{client_id}/jobs", response_model=list[JobOut])
async def list_jobs(
    client_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    c = await session.get(Client, client_id)
    if c is None:
        raise NotFound(f"client {client_id} not found")
    stmt = select(Job).where(Job.client_id == client_id).order_by(Job.queued_at.desc())
    if status:
        stmt = stmt.where(Job.status == status)
    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return [
        {
            "job_id": str(j.id),
            "endpoint": j.endpoint,
            "status": j.status,
            "pages_submitted": j.pages_submitted,
            "queued_at": j.queued_at,
            "completed_at": j.completed_at,
            "error_msg": j.error_msg,
        }
        for j in result.scalars().all()
    ]
