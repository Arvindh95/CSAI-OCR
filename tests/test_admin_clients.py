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
async def cleanup_emails():
    yield
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool,
                                  connect_args={"ssl": False})
    S = async_sessionmaker(engine, expire_on_commit=False)
    async with S() as s:
        await s.execute(text("DELETE FROM plans WHERE client_id IN (SELECT id FROM clients WHERE email LIKE 'admin-test-%')"))
        await s.execute(text("DELETE FROM clients WHERE email LIKE 'admin-test-%'"))
        await s.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_client_returns_key_once(cleanup_emails):
    with TestClient(app) as c:
        r = c.post("/admin/v1/clients", json={
            "name": "T1", "email": "admin-test-1@x.com",
            "max_transactions": 50, "max_pages_per_txn": 2,
        })
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["api_key"].startswith("ocr_live_")
        assert len(body["api_key"]) == 9 + 32
        assert body["api_key_prefix"] == body["api_key"][:12]
        assert body["is_active"] is True


@pytest.mark.asyncio
async def test_duplicate_email_rejected(cleanup_emails):
    with TestClient(app) as c:
        r1 = c.post("/admin/v1/clients", json={
            "name": "A", "email": "admin-test-2@x.com",
        })
        assert r1.status_code == 201
        r2 = c.post("/admin/v1/clients", json={
            "name": "B", "email": "admin-test-2@x.com",
        })
        assert r2.status_code == 400


@pytest.mark.asyncio
async def test_list_and_get_client(cleanup_emails):
    with TestClient(app) as c:
        r = c.post("/admin/v1/clients", json={
            "name": "Alpha", "email": "admin-test-3@x.com",
        })
        cid = r.json()["id"]
        lr = c.get("/admin/v1/clients")
        assert lr.status_code == 200
        ids = [x["id"] for x in lr.json()]
        assert cid in ids
        gr = c.get(f"/admin/v1/clients/{cid}")
        assert gr.status_code == 200
        assert gr.json()["email"] == "admin-test-3@x.com"
        # api_key NOT leaked
        assert "api_key" not in gr.json()


@pytest.mark.asyncio
async def test_get_nonexistent_client():
    with TestClient(app) as c:
        r = c.get("/admin/v1/clients/99999999")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_invalid_email_rejected():
    with TestClient(app) as c:
        r = c.post("/admin/v1/clients", json={"name": "X", "email": "not-email"})
        assert r.status_code == 400
