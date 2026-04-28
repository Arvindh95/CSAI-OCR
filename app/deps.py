from typing import AsyncIterator

from fastapi import Depends, Header, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.auth import authenticate
from app.billing.db import SessionLocal
from app.billing.models import Client
from app.billing.redis_client import get_redis
from app.errors import AuthError


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as s:
        yield s


async def get_redis_dep() -> AsyncIterator[Redis]:
    r = get_redis()
    try:
        yield r
    finally:
        await r.aclose()


async def current_client(
    request: Request,
    x_api_key: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Client:
    if not x_api_key:
        raise AuthError("missing X-API-Key")
    client = await authenticate(session, x_api_key)
    if client is None:
        raise AuthError("invalid api key")
    if not client.is_active:
        raise AuthError("client account is inactive")
    request.state.client_id = client.id
    return client
