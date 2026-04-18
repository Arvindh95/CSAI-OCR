import hashlib
import os
import secrets
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.billing.jobs import create_job, get_job, mark_done, mark_failed, mark_started
from app.billing.models import Client, Period, Plan


@pytest_asyncio.fixture
async def SessionLocal():
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_clients(SessionLocal):
    async with SessionLocal() as session:
        now = datetime.now(timezone.utc)
        c1 = Client(
            name="T1", email=f"t1-{secrets.token_hex(4)}@test",
            api_key_hash=hashlib.sha256(secrets.token_bytes(32)).digest(),
            api_key_prefix="ocr_live_t1", is_active=True, created_at=now,
        )
        c2 = Client(
            name="T2", email=f"t2-{secrets.token_hex(4)}@test",
            api_key_hash=hashlib.sha256(secrets.token_bytes(32)).digest(),
            api_key_prefix="ocr_live_t2", is_active=True, created_at=now,
        )
        session.add_all([c1, c2])
        await session.flush()
        p1 = Plan(client_id=c1.id, max_transactions=100, max_pages_per_txn=1,
                  reset_period="monthly", effective_from=now)
        p2 = Plan(client_id=c2.id, max_transactions=100, max_pages_per_txn=1,
                  reset_period="monthly", effective_from=now)
        session.add_all([p1, p2])
        period1 = Period(client_id=c1.id, period_start=now, period_end=now, is_open=True)
        period2 = Period(client_id=c2.id, period_start=now, period_end=now, is_open=True)
        session.add_all([period1, period2])
        await session.commit()
        c1_id, c2_id, p1_id, p2_id = c1.id, c2.id, period1.id, period2.id
    yield c1_id, c2_id, p1_id, p2_id
    async with SessionLocal() as session:
        await session.execute(text("DELETE FROM jobs WHERE client_id IN (:a, :b)"),
                              {"a": c1_id, "b": c2_id})
        await session.execute(text("DELETE FROM periods WHERE client_id IN (:a, :b)"),
                              {"a": c1_id, "b": c2_id})
        await session.execute(text("DELETE FROM plans WHERE client_id IN (:a, :b)"),
                              {"a": c1_id, "b": c2_id})
        await session.execute(text("DELETE FROM clients WHERE id IN (:a, :b)"),
                              {"a": c1_id, "b": c2_id})
        await session.commit()


@pytest.mark.asyncio
async def test_create_and_get_job(SessionLocal, seeded_clients):
    c1_id, _, p1_id, _ = seeded_clients
    async with SessionLocal() as session:
        job = await create_job(session, c1_id, p1_id, endpoint="/ocr", pages=2,
                                idempotency_key="k1", body_hash=b"\x01" * 32)
        await session.commit()
        jid = job.id
    async with SessionLocal() as session:
        fetched = await get_job(session, c1_id, jid)
        assert fetched is not None
        assert fetched.pages_submitted == 2
        assert fetched.status == "queued"
        assert fetched.idempotency_key == "k1"


@pytest.mark.asyncio
async def test_cross_client_isolation(SessionLocal, seeded_clients):
    c1_id, c2_id, p1_id, _ = seeded_clients
    async with SessionLocal() as session:
        job = await create_job(session, c1_id, p1_id, endpoint="/ocr")
        await session.commit()
        jid = job.id
    async with SessionLocal() as session:
        assert await get_job(session, c2_id, jid) is None
        assert await get_job(session, c1_id, jid) is not None


@pytest.mark.asyncio
async def test_get_nonexistent_job(SessionLocal, seeded_clients):
    c1_id, _, _, _ = seeded_clients
    async with SessionLocal() as session:
        assert await get_job(session, c1_id, uuid4()) is None


@pytest.mark.asyncio
async def test_mark_started_done(SessionLocal, seeded_clients):
    c1_id, _, p1_id, _ = seeded_clients
    async with SessionLocal() as session:
        job = await create_job(session, c1_id, p1_id, endpoint="/ocr")
        await session.commit()
        jid = job.id
    async with SessionLocal() as session:
        await mark_started(session, jid)
        await mark_done(session, jid, {"text": "hello"})
        await session.commit()
    async with SessionLocal() as session:
        fetched = await get_job(session, c1_id, jid)
        assert fetched.status == "done"
        assert fetched.attempts == 1
        assert fetched.result == {"text": "hello"}
        assert fetched.started_at is not None
        assert fetched.completed_at is not None


@pytest.mark.asyncio
async def test_mark_failed(SessionLocal, seeded_clients):
    c1_id, _, p1_id, _ = seeded_clients
    async with SessionLocal() as session:
        job = await create_job(session, c1_id, p1_id, endpoint="/ocr")
        await session.commit()
        jid = job.id
    async with SessionLocal() as session:
        await mark_failed(session, jid, "boom")
        await session.commit()
    async with SessionLocal() as session:
        fetched = await get_job(session, c1_id, jid)
        assert fetched.status == "failed"
        assert fetched.error_msg == "boom"
