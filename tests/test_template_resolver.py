import hashlib
import os
import secrets
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.billing.models import Client
from app.errors import Forbidden, NotFound
from app.templates.models import ClientTemplate, DocTemplate, TemplateField
from app.templates.resolver import load_template_dict, resolve_for_client


@pytest_asyncio.fixture
async def Session():
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool,
                                  connect_args={"ssl": False})
    s = async_sessionmaker(engine, expire_on_commit=False)
    yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def seed(Session):
    created = []
    now = datetime.now(timezone.utc)
    async with Session() as sess:
        c1 = Client(name="R1", email=f"rx1-{secrets.token_hex(4)}@example.com",
                    api_key_hash=hashlib.sha256(secrets.token_bytes(32)).digest(),
                    api_key_prefix="ocr_live_r1", is_active=True, created_at=now)
        c2 = Client(name="R2", email=f"rx2-{secrets.token_hex(4)}@example.com",
                    api_key_hash=hashlib.sha256(secrets.token_bytes(32)).digest(),
                    api_key_prefix="ocr_live_r2", is_active=True, created_at=now)
        sess.add_all([c1, c2])
        await sess.flush()
        code = f"rt-{secrets.token_hex(4)}"
        t_global = DocTemplate(client_id=None, name="G", doc_type_code=code,
                                version=1, is_active=True, created_at=now,
                                updated_at=now)
        sess.add(t_global)
        await sess.flush()
        sess.add(TemplateField(template_id=t_global.id, field_name="x",
                                page_index=0, strategy="regex",
                                config={"pattern": "x"}, required=False,
                                display_order=1))
        sess.add(ClientTemplate(client_id=c1.id, template_id=t_global.id, granted_at=now))
        await sess.commit()
        created = {"c1": c1.id, "c2": c2.id, "tpl": t_global.id, "code": code}
    yield created
    async with Session() as sess:
        await sess.execute(text("DELETE FROM client_templates WHERE template_id=:t"), {"t": created["tpl"]})
        await sess.execute(text("DELETE FROM template_fields WHERE template_id=:t"), {"t": created["tpl"]})
        await sess.execute(text("DELETE FROM doc_templates WHERE id=:t"), {"t": created["tpl"]})
        await sess.execute(text("DELETE FROM plans WHERE client_id IN (:a,:b)"),
                           {"a": created["c1"], "b": created["c2"]})
        await sess.execute(text("DELETE FROM clients WHERE id IN (:a,:b)"),
                           {"a": created["c1"], "b": created["c2"]})
        await sess.commit()


@pytest.mark.asyncio
async def test_resolve_whitelisted_ok(Session, seed):
    async with Session() as sess:
        t = await resolve_for_client(sess, seed["c1"], seed["code"])
        assert t.id == seed["tpl"]


@pytest.mark.asyncio
async def test_resolve_not_whitelisted_forbidden(Session, seed):
    async with Session() as sess:
        with pytest.raises(Forbidden):
            await resolve_for_client(sess, seed["c2"], seed["code"])


@pytest.mark.asyncio
async def test_resolve_unknown_code_notfound(Session, seed):
    async with Session() as sess:
        with pytest.raises(NotFound):
            await resolve_for_client(sess, seed["c1"], "never-exists-xyz")


@pytest.mark.asyncio
async def test_resolve_inactive_template_notfound(Session, seed):
    async with Session() as sess:
        t = await sess.get(DocTemplate, seed["tpl"])
        t.is_active = False
        await sess.commit()
    async with Session() as sess:
        with pytest.raises(NotFound):
            await resolve_for_client(sess, seed["c1"], seed["code"])


@pytest.mark.asyncio
async def test_load_template_dict_shape(Session, seed):
    async with Session() as sess:
        d = await load_template_dict(sess, seed["tpl"])
    assert d["template_id"] == seed["tpl"]
    assert d["version"] == 1
    assert d["fields"][0]["name"] == "x"
    assert isinstance(d["pages"], list)
