import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.main import app


@pytest_asyncio.fixture(autouse=True)
async def dispose_app_engine():
    yield
    from app.billing import db
    await db.engine.dispose()


@pytest_asyncio.fixture
async def cleanup():
    yield
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool,
                                  connect_args={"ssl": False})
    S = async_sessionmaker(engine, expire_on_commit=False)
    async with S() as s:
        await s.execute(text("DELETE FROM jobs WHERE client_id IN (SELECT id FROM clients WHERE email LIKE 'use-test-%')"))
        await s.execute(text("DELETE FROM periods WHERE client_id IN (SELECT id FROM clients WHERE email LIKE 'use-test-%')"))
        await s.execute(text("DELETE FROM plans WHERE client_id IN (SELECT id FROM clients WHERE email LIKE 'use-test-%')"))
        await s.execute(text("DELETE FROM clients WHERE email LIKE 'use-test-%'"))
        await s.commit()
    await engine.dispose()
    import redis.asyncio as aioredis
    r = aioredis.from_url("redis://127.0.0.1:6379/0")
    async for k in r.scan_iter("quota:*"):
        pass
    await r.aclose()


def _new(c, email, max_txn=100):
    return c.post("/admin/v1/clients", json={
        "name": "U", "email": email,
        "max_transactions": max_txn, "max_pages_per_txn": 1,
    }).json()


@pytest.mark.asyncio
async def test_usage_zero_initial(cleanup):
    with TestClient(app) as c:
        cid = _new(c, "use-test-a@x.com", max_txn=50)["id"]
        r = c.get(f"/admin/v1/clients/{cid}/usage")
        assert r.status_code == 200
        body = r.json()
        assert body["used"] == 0
        assert body["limit"] == 50
        assert body["remaining"] == 50


@pytest.mark.asyncio
async def test_quota_reset(cleanup):
    import redis.asyncio as aioredis
    with TestClient(app) as c:
        cid = _new(c, "use-test-b@x.com", max_txn=10)["id"]
        ur = c.get(f"/admin/v1/clients/{cid}/usage").json()
        pid = ur["period_id"]
        r = aioredis.from_url("redis://127.0.0.1:6379/0")
        await r.set(f"quota:{cid}:{pid}", 7, ex=3600)
        await r.aclose()
        before = c.get(f"/admin/v1/clients/{cid}/usage").json()
        assert before["used"] == 7
        rr = c.post(f"/admin/v1/clients/{cid}/quota/reset")
        assert rr.status_code == 200
        assert rr.json()["used"] == 0
        after = c.get(f"/admin/v1/clients/{cid}/usage").json()
        assert after["used"] == 0


@pytest.mark.asyncio
async def test_list_jobs_empty_and_filter(cleanup):
    with TestClient(app) as c:
        cid = _new(c, "use-test-c@x.com")["id"]
        r = c.get(f"/admin/v1/clients/{cid}/jobs")
        assert r.status_code == 200
        assert r.json() == []


@pytest.mark.asyncio
async def test_list_jobs_with_inserts(cleanup):
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool,
                                  connect_args={"ssl": False})
    S = async_sessionmaker(engine, expire_on_commit=False)
    with TestClient(app) as c:
        cid = _new(c, "use-test-d@x.com")["id"]
        ur = c.get(f"/admin/v1/clients/{cid}/usage").json()
        pid = ur["period_id"]
        now = datetime.now(timezone.utc)
        async with S() as s:
            from app.billing.models import Job
            for st in ("queued", "done", "failed"):
                s.add(Job(id=uuid4(), client_id=cid, period_id=pid,
                          endpoint="/api/v1/ocr", status=st,
                          pages_submitted=1, attempts=0,
                          queued_at=now))
            await s.commit()
        r = c.get(f"/admin/v1/clients/{cid}/jobs")
        assert r.status_code == 200
        assert len(r.json()) == 3
        r2 = c.get(f"/admin/v1/clients/{cid}/jobs?status=done")
        assert len(r2.json()) == 1
        assert r2.json()[0]["status"] == "done"
    await engine.dispose()


@pytest.mark.asyncio
async def test_usage_unknown_client():
    with TestClient(app) as c:
        r = c.get("/admin/v1/clients/99999999/usage")
        assert r.status_code == 404
