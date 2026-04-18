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
        await s.execute(text("DELETE FROM plans WHERE client_id IN (SELECT id FROM clients WHERE email LIKE 'lc-test-%')"))
        await s.execute(text("DELETE FROM clients WHERE email LIKE 'lc-test-%'"))
        await s.commit()
    await engine.dispose()


def _make(c, email, name="X"):
    r = c.post("/admin/v1/clients", json={"name": name, "email": email})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_patch_name_and_email(cleanup):
    with TestClient(app) as c:
        cid = _make(c, "lc-test-a@x.com")["id"]
        r = c.patch(f"/admin/v1/clients/{cid}",
                    json={"name": "Renamed", "email": "lc-test-a2@x.com"})
        assert r.status_code == 200
        assert r.json()["name"] == "Renamed"
        assert r.json()["email"] == "lc-test-a2@x.com"


@pytest.mark.asyncio
async def test_patch_deactivate(cleanup):
    with TestClient(app) as c:
        cid = _make(c, "lc-test-b@x.com")["id"]
        r = c.patch(f"/admin/v1/clients/{cid}", json={"is_active": False})
        assert r.status_code == 200
        assert r.json()["is_active"] is False


@pytest.mark.asyncio
async def test_patch_email_conflict(cleanup):
    with TestClient(app) as c:
        _make(c, "lc-test-c@x.com")
        cid2 = _make(c, "lc-test-d@x.com")["id"]
        r = c.patch(f"/admin/v1/clients/{cid2}", json={"email": "lc-test-c@x.com"})
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_rotate_key_returns_new_and_invalidates_old(cleanup):
    with TestClient(app) as c:
        created = _make(c, "lc-test-e@x.com")
        old_key = created["api_key"]
        old_prefix = created["api_key_prefix"]
        r = c.post(f"/admin/v1/clients/{created['id']}/rotate-key")
        assert r.status_code == 200
        new_key = r.json()["api_key"]
        assert new_key != old_key
        assert new_key.startswith("ocr_live_")
        assert r.json()["api_key_prefix"] != old_prefix


@pytest.mark.asyncio
async def test_delete_soft_deactivates(cleanup):
    with TestClient(app) as c:
        cid = _make(c, "lc-test-f@x.com")["id"]
        r = c.delete(f"/admin/v1/clients/{cid}")
        assert r.status_code == 200
        assert r.json()["is_active"] is False
        g = c.get(f"/admin/v1/clients/{cid}")
        assert g.status_code == 200
        assert g.json()["is_active"] is False


@pytest.mark.asyncio
async def test_patch_unknown_client():
    with TestClient(app) as c:
        r = c.patch("/admin/v1/clients/99999999", json={"is_active": False})
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_rotate_unknown_client():
    with TestClient(app) as c:
        r = c.post("/admin/v1/clients/99999999/rotate-key")
        assert r.status_code == 404
