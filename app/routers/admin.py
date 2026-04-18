from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.schemas import (
    ClientCreate,
    ClientCreated,
    ClientOut,
    ClientUpdate,
)
from app.billing.auth import generate_api_key, hash_api_key, key_prefix
from app.billing.models import Client, Plan
from app.deps import get_session
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


@router.delete("/clients/{client_id}", response_model=ClientOut)
async def deactivate_client(client_id: int, session: AsyncSession = Depends(get_session)):
    c = await session.get(Client, client_id)
    if c is None:
        raise NotFound(f"client {client_id} not found")
    c.is_active = False
    await session.commit()
    await session.refresh(c)
    return _client_out(c)
