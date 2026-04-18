import os

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
        await s.execute(text("DELETE FROM plans WHERE client_id IN (SELECT id FROM clients WHERE email LIKE 'plan-test-%')"))
        await s.execute(text("DELETE FROM clients WHERE email LIKE 'plan-test-%'"))
        await s.commit()
    await engine.dispose()


def _new(c, email):
    return c.post("/admin/v1/clients", json={
        "name": "P", "email": email,
        "max_transactions": 100, "max_pages_per_txn": 1,
    }).json()


@pytest.mark.asyncio
async def test_get_current_plan(cleanup):
    with TestClient(app) as c:
        cid = _new(c, "plan-test-a@x.com")["id"]
        r = c.get(f"/admin/v1/clients/{cid}/plan")
        assert r.status_code == 200
        assert r.json()["max_transactions"] == 100
        assert r.json()["effective_to"] is None


@pytest.mark.asyncio
async def test_upsert_supersedes_old_plan(cleanup):
    with TestClient(app) as c:
        cid = _new(c, "plan-test-b@x.com")["id"]
        r = c.put(f"/admin/v1/clients/{cid}/plan",
                  json={"max_transactions": 500, "max_pages_per_txn": 3,
                        "reset_period": "lifetime"})
        assert r.status_code == 200
        assert r.json()["max_transactions"] == 500
        assert r.json()["reset_period"] == "lifetime"
        cur = c.get(f"/admin/v1/clients/{cid}/plan").json()
        assert cur["max_transactions"] == 500


@pytest.mark.asyncio
async def test_upsert_unknown_client():
    with TestClient(app) as c:
        r = c.put("/admin/v1/clients/99999999/plan",
                  json={"max_transactions": 10})
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_upsert_rejects_bad_reset_period(cleanup):
    with TestClient(app) as c:
        cid = _new(c, "plan-test-c@x.com")["id"]
        r = c.put(f"/admin/v1/clients/{cid}/plan",
                  json={"max_transactions": 10, "reset_period": "yearly"})
        assert r.status_code == 400
