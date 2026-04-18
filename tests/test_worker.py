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
                        lambda p: [{"text": "hi", "confidence": 0.9, "page_index": 0}])
    async with Session() as sess:
        job = await create_job(sess, cid, pid, endpoint="/ocr")
        await sess.commit()
        jid = job.id
    await worker._process(jid, str(fake_file), cid, pid)
    async with Session() as sess:
        fetched = await get_job(sess, cid, jid)
        assert fetched.status == "done"
        assert fetched.result["joined"] == "hi"
        assert len(fetched.result["lines"]) == 1
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
    await worker._process(jid, str(fake_file), cid, pid)
    async with Session() as sess:
        fetched = await get_job(sess, cid, jid)
        assert fetched.status == "failed"
        assert "ocr exploded" in fetched.error_msg


@pytest.mark.asyncio
async def test_worker_applies_template(Session, seeded, monkeypatch, tmp_path):
    from app.templates.models import DocTemplate, TemplateField, TemplatePage
    cid, pid = seeded
    fake_file = tmp_path / "x.png"
    fake_file.write_bytes(b"fake")
    now = datetime.now(timezone.utc)
    async with Session() as sess:
        t = DocTemplate(client_id=None, name="T", doc_type_code=f"t-{secrets.token_hex(4)}",
                        version=1, is_active=True, created_at=now, updated_at=now)
        sess.add(t)
        await sess.flush()
        sess.add(TemplatePage(template_id=t.id, page_index=0,
                              image_path="/tmp/x.png", image_width=1200,
                              image_height=1600))
        sess.add(TemplateField(
            template_id=t.id, field_name="invoice_no", page_index=0,
            strategy="anchor",
            config={"labels": ["INVOICE NO"], "direction": "right",
                    "max_distance_px": 300},
            post_process="trim", required=True, display_order=1,
        ))
        await sess.commit()
        tid = t.id
    monkeypatch.setattr(worker, "_run_paddle", lambda p: [
        {"text": "INVOICE NO", "confidence": 0.9, "page_index": 0,
         "bbox": [10, 10, 100, 20]},
        {"text": "INV-42", "confidence": 0.95, "page_index": 0,
         "bbox": [150, 10, 80, 20]},
    ])
    async with Session() as sess:
        job = await create_job(sess, cid, pid, endpoint="/ocr",
                                template_id=tid, template_version=1)
        await sess.commit()
        jid = job.id
    await worker._process(jid, str(fake_file), cid, pid, template_id=tid)
    async with Session() as sess:
        fetched = await get_job(sess, cid, jid)
        assert fetched.status == "done"
        assert fetched.result["template_id"] == tid
        assert fetched.result["template_version"] == 1
        assert fetched.result["fields"]["invoice_no"] == "INV-42"
        await sess.execute(text("UPDATE jobs SET template_id = NULL WHERE template_id = :t"), {"t": tid})
        await sess.execute(text("DELETE FROM template_fields WHERE template_id = :t"), {"t": tid})
        await sess.execute(text("DELETE FROM template_pages WHERE template_id = :t"), {"t": tid})
        await sess.execute(text("DELETE FROM doc_templates WHERE id = :t"), {"t": tid})
        await sess.commit()
