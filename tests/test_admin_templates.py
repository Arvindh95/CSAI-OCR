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
async def cleanup_templates():
    yield
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool,
                                  connect_args={"ssl": False})
    S = async_sessionmaker(engine, expire_on_commit=False)
    async with S() as s:
        await s.execute(text("DELETE FROM template_fields WHERE template_id IN "
                             "(SELECT id FROM doc_templates WHERE doc_type_code LIKE 'tpl-test-%')"))
        await s.execute(text("DELETE FROM template_pages WHERE template_id IN "
                             "(SELECT id FROM doc_templates WHERE doc_type_code LIKE 'tpl-test-%')"))
        await s.execute(text("DELETE FROM client_templates WHERE template_id IN "
                             "(SELECT id FROM doc_templates WHERE doc_type_code LIKE 'tpl-test-%')"))
        await s.execute(text("DELETE FROM doc_templates WHERE doc_type_code LIKE 'tpl-test-%'"))
        await s.execute(text("DELETE FROM plans WHERE client_id IN "
                             "(SELECT id FROM clients WHERE email LIKE 'tpl-test-%')"))
        await s.execute(text("DELETE FROM clients WHERE email LIKE 'tpl-test-%'"))
        await s.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_template_basic(cleanup_templates):
    with TestClient(app) as c:
        r = c.post("/admin/v1/templates", json={
            "name": "Test Tpl 1",
            "doc_type_code": "tpl-test-1",
            "fields": [
                {"name": "invoice_no", "page_index": 0, "strategy": "anchor",
                 "config": {"labels": ["INVOICE NO"], "direction": "right"},
                 "post_process": "trim", "required": True, "display_order": 1},
                {"name": "total", "page_index": 0, "strategy": "regex",
                 "config": {"pattern": r"TOTAL:\s*([\d.]+)", "group": 1},
                 "post_process": "number", "required": False, "display_order": 2},
            ],
        })
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["doc_type_code"] == "tpl-test-1"
        assert body["version"] == 1
        assert body["is_active"] is True
        assert len(body["fields"]) == 2
        names = [f["name"] for f in body["fields"]]
        assert names == ["invoice_no", "total"]


@pytest.mark.asyncio
async def test_create_duplicate_active_code_rejected(cleanup_templates):
    with TestClient(app) as c:
        c.post("/admin/v1/templates", json={
            "name": "A", "doc_type_code": "tpl-test-dup", "fields": []})
        r = c.post("/admin/v1/templates", json={
            "name": "B", "doc_type_code": "tpl-test-dup", "fields": []})
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_list_and_get_template(cleanup_templates):
    with TestClient(app) as c:
        cr = c.post("/admin/v1/templates", json={
            "name": "ListMe", "doc_type_code": "tpl-test-list", "fields": []})
        tid = cr.json()["id"]
        lst = c.get("/admin/v1/templates?doc_type_code=tpl-test-list").json()
        assert any(t["id"] == tid for t in lst)
        detail = c.get(f"/admin/v1/templates/{tid}").json()
        assert detail["doc_type_code"] == "tpl-test-list"
        assert detail["pages"] == []
        assert detail["fields"] == []


@pytest.mark.asyncio
async def test_update_template_creates_new_version(cleanup_templates):
    with TestClient(app) as c:
        cr = c.post("/admin/v1/templates", json={
            "name": "V1", "doc_type_code": "tpl-test-ver",
            "fields": [{"name": "f1", "page_index": 0, "strategy": "regex",
                        "config": {"pattern": "x"}, "required": False,
                        "display_order": 1}]})
        tid = cr.json()["id"]
        up = c.put(f"/admin/v1/templates/{tid}", json={
            "name": "V2",
            "fields": [{"name": "f1", "page_index": 0, "strategy": "regex",
                        "config": {"pattern": "y"}, "required": False,
                        "display_order": 1}]})
        assert up.status_code == 200
        new_body = up.json()
        assert new_body["version"] == 2
        assert new_body["name"] == "V2"
        assert new_body["id"] != tid
        old = c.get(f"/admin/v1/templates/{tid}").json()
        assert old["is_active"] is False
        active_by_code = c.get("/admin/v1/templates?doc_type_code=tpl-test-ver&active_only=true").json()
        assert len(active_by_code) == 1
        assert active_by_code[0]["version"] == 2


@pytest.mark.asyncio
async def test_update_inactive_rejected(cleanup_templates):
    with TestClient(app) as c:
        cr = c.post("/admin/v1/templates", json={
            "name": "x", "doc_type_code": "tpl-test-inact", "fields": []})
        tid = cr.json()["id"]
        c.delete(f"/admin/v1/templates/{tid}")
        r = c.put(f"/admin/v1/templates/{tid}", json={"name": "y"})
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_delete_soft(cleanup_templates):
    with TestClient(app) as c:
        cr = c.post("/admin/v1/templates", json={
            "name": "d", "doc_type_code": "tpl-test-del", "fields": []})
        tid = cr.json()["id"]
        r = c.delete(f"/admin/v1/templates/{tid}")
        assert r.status_code == 200
        assert r.json()["is_active"] is False
        d = c.get(f"/admin/v1/templates/{tid}").json()
        assert d["is_active"] is False


@pytest.mark.asyncio
async def test_upload_page_image(cleanup_templates, tmp_path):
    from PIL import Image
    img_path = tmp_path / "sample.png"
    Image.new("RGB", (640, 480), "white").save(img_path, format="PNG")
    with TestClient(app) as c:
        cr = c.post("/admin/v1/templates", json={
            "name": "p", "doc_type_code": "tpl-test-pg", "fields": []})
        tid = cr.json()["id"]
        with open(img_path, "rb") as f:
            up = c.post(
                f"/admin/v1/templates/{tid}/pages",
                data={"page_index": "0"},
                files={"file": ("sample.png", f, "image/png")},
            )
        assert up.status_code == 200, up.text
        pg = up.json()
        assert pg["page_index"] == 0
        assert pg["image_width"] == 640
        assert pg["image_height"] == 480
        detail = c.get(f"/admin/v1/templates/{tid}").json()
        assert len(detail["pages"]) == 1
        dr = c.delete(f"/admin/v1/templates/{tid}/pages/0")
        assert dr.status_code == 200
        detail2 = c.get(f"/admin/v1/templates/{tid}").json()
        assert detail2["pages"] == []


@pytest.mark.asyncio
async def test_client_whitelist_grant_list_revoke(cleanup_templates):
    with TestClient(app) as c:
        cr = c.post("/admin/v1/clients", json={
            "name": "TG", "email": "tpl-test-grant@x.com"})
        assert cr.status_code == 201
        cid = cr.json()["id"]
        tr = c.post("/admin/v1/templates", json={
            "name": "w", "doc_type_code": "tpl-test-wl", "fields": []})
        tid = tr.json()["id"]

        g = c.post(f"/admin/v1/clients/{cid}/templates", json={"template_id": tid})
        assert g.status_code == 201
        lst = c.get(f"/admin/v1/clients/{cid}/templates").json()
        assert [t["id"] for t in lst] == [tid]

        g2 = c.post(f"/admin/v1/clients/{cid}/templates", json={"template_id": tid})
        assert g2.status_code == 201

        rv = c.delete(f"/admin/v1/clients/{cid}/templates/{tid}")
        assert rv.status_code == 200
        lst2 = c.get(f"/admin/v1/clients/{cid}/templates").json()
        assert lst2 == []


@pytest.mark.asyncio
async def test_grant_missing_template_404(cleanup_templates):
    with TestClient(app) as c:
        cr = c.post("/admin/v1/clients", json={
            "name": "X", "email": "tpl-test-404@x.com"})
        cid = cr.json()["id"]
        g = c.post(f"/admin/v1/clients/{cid}/templates", json={"template_id": 99999999})
        assert g.status_code == 404


@pytest.mark.asyncio
async def test_create_template_rejects_bad_doc_type_code(cleanup_templates):
    with TestClient(app) as c:
        r = c.post("/admin/v1/templates", json={
            "name": "bad", "doc_type_code": "Has Spaces!", "fields": []})
        assert r.status_code in (400, 422)
