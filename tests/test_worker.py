import hashlib
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.billing.jobs import create_job, get_job
from app.billing.models import Client, Period, Plan
from app import worker


@pytest_asyncio.fixture
async def Session():
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    s = async_sessionmaker(engine, expire_on_commit=False)
    yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded(Session):
    async with Session() as sess:
        now = datetime.now(timezone.utc)
        c = Client(
            name="W", email=f"w-{secrets.token_hex(4)}@test",
            api_key_hash=hashlib.sha256(secrets.token_bytes(32)).digest(),
            api_key_prefix="ocr_live_w", is_active=True, created_at=now,
        )
        sess.add(c)
        await sess.flush()
        sess.add(Plan(client_id=c.id, max_transactions=100, max_pages_per_txn=1,
                      reset_period="monthly", effective_from=now))
        p = Period(client_id=c.id, period_start=now, period_end=now, is_open=True)
        sess.add(p)
        await sess.commit()
        cid, pid = c.id, p.id
    yield cid, pid
    async with Session() as sess:
        await sess.execute(text("DELETE FROM usage_log WHERE client_id = :c"), {"c": cid})
        await sess.execute(text("DELETE FROM jobs WHERE client_id = :c"), {"c": cid})
        await sess.execute(text("DELETE FROM periods WHERE client_id = :c"), {"c": cid})
        await sess.execute(text("DELETE FROM plans WHERE client_id = :c"), {"c": cid})
        await sess.execute(text("DELETE FROM clients WHERE id = :c"), {"c": cid})
        await sess.commit()


@pytest.mark.asyncio
async def test_worker_success_path(Session, seeded, monkeypatch, tmp_path):
    cid, pid = seeded
    fake_file = tmp_path / "x.png"
    fake_file.write_bytes(b"fake")
    monkeypatch.setattr(worker, "_run_paddle",
                        lambda p: {"text_lines": ["hi"], "joined": "hi"})
    async with Session() as sess:
        job = await create_job(sess, cid, pid, endpoint="/ocr")
        await sess.commit()
        jid = job.id
    worker.run_ocr_job(str(jid), "/ocr", str(fake_file), cid, pid)
    async with Session() as sess:
        fetched = await get_job(sess, cid, jid)
        assert fetched.status == "done"
        assert fetched.result == {"text_lines": ["hi"], "joined": "hi"}
        assert fetched.started_at is not None
        assert fetched.completed_at is not None
    assert not fake_file.exists()


@pytest.mark.asyncio
async def test_worker_failure_path(Session, seeded, monkeypatch, tmp_path):
    cid, pid = seeded
    fake_file = tmp_path / "x.png"
    fake_file.write_bytes(b"fake")
    def boom(p):
        raise RuntimeError("ocr exploded")
    monkeypatch.setattr(worker, "_run_paddle", boom)
    async with Session() as sess:
        job = await create_job(sess, cid, pid, endpoint="/ocr")
        await sess.commit()
        jid = job.id
    worker.run_ocr_job(str(jid), "/ocr", str(fake_file), cid, pid)
    async with Session() as sess:
        fetched = await get_job(sess, cid, jid)
        assert fetched.status == "failed"
        assert "ocr exploded" in fetched.error_msg
