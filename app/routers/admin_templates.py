import asyncio
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from PIL import Image
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.templates_schemas import (
    FieldOut,
    GrantIn,
    GrantOut,
    PageOut,
    TemplateCreate,
    TemplateListItem,
    TemplateOut,
    TemplateUpdate,
    TestResult,
)
from app.billing.models import Client
from app.deps import get_session
from app.errors import BadRequest, NotFound
from app.templates.extractor import extract_with_template
from app.templates.models import (
    ClientTemplate,
    DocTemplate,
    TemplateField,
    TemplatePage,
)

router = APIRouter(prefix="/admin/v1")

TEMPLATES_ROOT = Path(os.environ.get("TEMPLATES_DIR", "/opt/ocr-saas/templates"))


def _template_dir(template_id: int) -> Path:
    d = TEMPLATES_ROOT / str(template_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


async def _load_pages(session: AsyncSession, template_id: int) -> list[TemplatePage]:
    r = await session.execute(
        select(TemplatePage).where(TemplatePage.template_id == template_id)
        .order_by(TemplatePage.page_index)
    )
    return list(r.scalars().all())


async def _load_fields(session: AsyncSession, template_id: int) -> list[TemplateField]:
    r = await session.execute(
        select(TemplateField).where(TemplateField.template_id == template_id)
        .order_by(TemplateField.display_order, TemplateField.id)
    )
    return list(r.scalars().all())


def _field_out(f: TemplateField) -> dict:
    return {
        "id": f.id, "name": f.field_name, "page_index": f.page_index,
        "strategy": f.strategy, "config": f.config,
        "post_process": f.post_process, "required": f.required,
        "display_order": f.display_order,
    }


def _page_out(p: TemplatePage) -> dict:
    return {
        "page_index": p.page_index, "image_path": p.image_path,
        "image_width": p.image_width, "image_height": p.image_height,
    }


async def _template_detail(session: AsyncSession, t: DocTemplate) -> dict:
    pages = await _load_pages(session, t.id)
    fields = await _load_fields(session, t.id)
    return {
        "id": t.id, "client_id": t.client_id, "name": t.name,
        "doc_type_code": t.doc_type_code, "version": t.version,
        "is_active": t.is_active, "created_by": t.created_by,
        "created_at": t.created_at, "updated_at": t.updated_at,
        "pages": [_page_out(p) for p in pages],
        "fields": [_field_out(f) for f in fields],
    }


@router.post("/templates", response_model=TemplateOut, status_code=201)
async def create_template(
    body: TemplateCreate,
    session: AsyncSession = Depends(get_session),
):
    if body.client_id is not None:
        if await session.get(Client, body.client_id) is None:
            raise NotFound(f"client {body.client_id} not found")
    now = datetime.now(timezone.utc)
    t = DocTemplate(
        client_id=body.client_id, name=body.name,
        doc_type_code=body.doc_type_code, version=1, is_active=True,
        created_at=now, updated_at=now,
    )
    session.add(t)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise BadRequest(f"doc_type_code already active: {body.doc_type_code}")
    for f in body.fields:
        session.add(TemplateField(
            template_id=t.id, field_name=f.name, page_index=f.page_index,
            strategy=f.strategy, config=f.config, post_process=f.post_process,
            required=f.required, display_order=f.display_order,
        ))
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise BadRequest(f"field conflict: {e.orig}")
    return await _template_detail(session, t)


@router.get("/templates", response_model=list[TemplateListItem])
async def list_templates(
    active_only: bool = False,
    doc_type_code: str | None = Query(default=None),
    client_id: int | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(DocTemplate).order_by(DocTemplate.id.desc())
    if active_only:
        stmt = stmt.where(DocTemplate.is_active.is_(True))
    if doc_type_code:
        stmt = stmt.where(DocTemplate.doc_type_code == doc_type_code)
    if client_id is not None:
        stmt = stmt.where(DocTemplate.client_id == client_id)
    r = await session.execute(stmt)
    return [
        {"id": t.id, "client_id": t.client_id, "name": t.name,
         "doc_type_code": t.doc_type_code, "version": t.version,
         "is_active": t.is_active, "created_at": t.created_at}
        for t in r.scalars().all()
    ]


@router.get("/templates/{template_id}", response_model=TemplateOut)
async def get_template(template_id: int, session: AsyncSession = Depends(get_session)):
    t = await session.get(DocTemplate, template_id)
    if t is None:
        raise NotFound(f"template {template_id} not found")
    return await _template_detail(session, t)


@router.put("/templates/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: int,
    body: TemplateUpdate,
    session: AsyncSession = Depends(get_session),
):
    old = await session.get(DocTemplate, template_id)
    if old is None:
        raise NotFound(f"template {template_id} not found")
    if not old.is_active:
        raise BadRequest("cannot update inactive template; create new instead")

    now = datetime.now(timezone.utc)
    old.is_active = False
    old.updated_at = now
    await session.flush()

    new = DocTemplate(
        client_id=old.client_id,
        name=body.name or old.name,
        doc_type_code=old.doc_type_code,
        version=old.version + 1,
        is_active=True,
        created_by=old.created_by,
        created_at=now, updated_at=now,
    )
    session.add(new)
    await session.flush()

    old_pages = await _load_pages(session, old.id)
    for p in old_pages:
        session.add(TemplatePage(
            template_id=new.id, page_index=p.page_index,
            image_path=p.image_path, image_width=p.image_width,
            image_height=p.image_height,
        ))

    if body.fields is not None:
        fields_spec = body.fields
    else:
        old_fields = await _load_fields(session, old.id)
        fields_spec = [
            type("F", (), {
                "name": f.field_name, "page_index": f.page_index,
                "strategy": f.strategy, "config": f.config,
                "post_process": f.post_process, "required": f.required,
                "display_order": f.display_order,
            })() for f in old_fields
        ]
    for f in fields_spec:
        session.add(TemplateField(
            template_id=new.id, field_name=f.name, page_index=f.page_index,
            strategy=f.strategy, config=f.config, post_process=f.post_process,
            required=f.required, display_order=f.display_order,
        ))
    await session.commit()
    return await _template_detail(session, new)


@router.delete("/templates/{template_id}", response_model=TemplateListItem)
async def delete_template(template_id: int, session: AsyncSession = Depends(get_session)):
    t = await session.get(DocTemplate, template_id)
    if t is None:
        raise NotFound(f"template {template_id} not found")
    t.is_active = False
    t.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(t)
    return {"id": t.id, "client_id": t.client_id, "name": t.name,
            "doc_type_code": t.doc_type_code, "version": t.version,
            "is_active": t.is_active, "created_at": t.created_at}


@router.post("/templates/{template_id}/pages", response_model=PageOut)
async def upload_page(
    template_id: int,
    page_index: int = Form(..., ge=0),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    t = await session.get(DocTemplate, template_id)
    if t is None:
        raise NotFound(f"template {template_id} not found")
    data = await file.read()
    if not data:
        raise BadRequest("empty file")
    try:
        img = Image.open(__import__("io").BytesIO(data))
        img.load()
        width, height = img.size
    except Exception as e:
        raise BadRequest(f"invalid image: {e}")

    suffix = (file.filename or "page").rsplit(".", 1)[-1].lower()
    if suffix not in ("jpg", "jpeg", "png"):
        suffix = "png"
    dest = _template_dir(template_id) / f"page_{page_index}.{suffix}"
    dest.write_bytes(data)

    existing = await session.get(TemplatePage, (template_id, page_index))
    if existing is not None:
        existing.image_path = str(dest)
        existing.image_width = width
        existing.image_height = height
        row = existing
    else:
        row = TemplatePage(
            template_id=template_id, page_index=page_index,
            image_path=str(dest), image_width=width, image_height=height,
        )
        session.add(row)
    t.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return _page_out(row)


@router.delete("/templates/{template_id}/pages/{page_index}")
async def delete_page(template_id: int, page_index: int,
                      session: AsyncSession = Depends(get_session)):
    row = await session.get(TemplatePage, (template_id, page_index))
    if row is None:
        raise NotFound(f"page {page_index} not found on template {template_id}")
    try:
        Path(row.image_path).unlink(missing_ok=True)
    except Exception:
        pass
    await session.delete(row)
    await session.commit()
    return {"deleted": True, "template_id": template_id, "page_index": page_index}


def _run_ocr_sync(path: str) -> list[dict]:
    from app.ocr import extract_lines, get_ocr
    return extract_lines(get_ocr(), path)


@router.post("/templates/{template_id}/test", response_model=TestResult)
async def test_template(
    template_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    t = await session.get(DocTemplate, template_id)
    if t is None:
        raise NotFound(f"template {template_id} not found")
    data = await file.read()
    if not data:
        raise BadRequest("empty file")
    suffix = (file.filename or "x").rsplit(".", 1)[-1].lower()
    if suffix not in ("jpg", "jpeg", "png", "pdf"):
        suffix = "png"
    with tempfile.NamedTemporaryFile(suffix=f".{suffix}", delete=False) as f:
        f.write(data)
        tmp_path = f.name
    try:
        loop = asyncio.get_event_loop()
        lines = await loop.run_in_executor(None, _run_ocr_sync, tmp_path)
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass

    pages = await _load_pages(session, template_id)
    fields = await _load_fields(session, template_id)
    template_dict = {
        "pages": [
            {"page_index": p.page_index, "width": p.image_width,
             "height": p.image_height} for p in pages
        ],
        "fields": [
            {"name": f.field_name, "page_index": f.page_index,
             "strategy": f.strategy, "config": f.config,
             "post_process": f.post_process, "required": f.required,
             "display_order": f.display_order}
            for f in fields
        ],
    }
    extracted = extract_with_template(lines, template_dict)
    return {"lines": lines, "extracted": extracted}


@router.get("/clients/{client_id}/templates", response_model=list[TemplateListItem])
async def list_client_templates(
    client_id: int, session: AsyncSession = Depends(get_session),
):
    c = await session.get(Client, client_id)
    if c is None:
        raise NotFound(f"client {client_id} not found")
    stmt = (
        select(DocTemplate)
        .join(ClientTemplate, ClientTemplate.template_id == DocTemplate.id)
        .where(ClientTemplate.client_id == client_id)
        .order_by(DocTemplate.id.desc())
    )
    r = await session.execute(stmt)
    return [
        {"id": t.id, "client_id": t.client_id, "name": t.name,
         "doc_type_code": t.doc_type_code, "version": t.version,
         "is_active": t.is_active, "created_at": t.created_at}
        for t in r.scalars().all()
    ]


@router.post("/clients/{client_id}/templates", response_model=GrantOut, status_code=201)
async def grant_template(
    client_id: int, body: GrantIn,
    session: AsyncSession = Depends(get_session),
):
    c = await session.get(Client, client_id)
    if c is None:
        raise NotFound(f"client {client_id} not found")
    t = await session.get(DocTemplate, body.template_id)
    if t is None:
        raise NotFound(f"template {body.template_id} not found")
    existing = await session.get(ClientTemplate, (client_id, body.template_id))
    if existing is not None:
        return {"client_id": client_id, "template_id": body.template_id,
                "granted_at": existing.granted_at}
    now = datetime.now(timezone.utc)
    row = ClientTemplate(client_id=client_id, template_id=body.template_id,
                         granted_at=now)
    session.add(row)
    await session.commit()
    return {"client_id": client_id, "template_id": body.template_id,
            "granted_at": now}


@router.delete("/clients/{client_id}/templates/{template_id}")
async def revoke_template(
    client_id: int, template_id: int,
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(ClientTemplate, (client_id, template_id))
    if row is None:
        raise NotFound(f"grant not found: client={client_id} template={template_id}")
    await session.delete(row)
    await session.commit()
    return {"revoked": True, "client_id": client_id, "template_id": template_id}
