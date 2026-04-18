from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import Forbidden, NotFound
from app.templates.models import (
    ClientTemplate,
    DocTemplate,
    TemplateField,
    TemplatePage,
)


async def resolve_for_client(
    session: AsyncSession, client_id: int, doc_type_code: str
) -> DocTemplate:
    r = await session.execute(
        select(DocTemplate).where(
            DocTemplate.doc_type_code == doc_type_code,
            DocTemplate.is_active.is_(True),
        )
    )
    t = r.scalar_one_or_none()
    if t is None:
        raise NotFound(f"no active template for doc_type={doc_type_code}")
    if t.client_id is not None and t.client_id != client_id:
        raise Forbidden(f"doc_type={doc_type_code} not available to this client")
    grant = await session.get(ClientTemplate, (client_id, t.id))
    if grant is None and t.client_id is None:
        raise Forbidden(f"doc_type={doc_type_code} not whitelisted for this client")
    return t


async def load_template_dict(session: AsyncSession, template_id: int) -> dict:
    t = await session.get(DocTemplate, template_id)
    if t is None:
        raise NotFound(f"template {template_id} not found")
    pr = await session.execute(
        select(TemplatePage).where(TemplatePage.template_id == template_id)
    )
    fr = await session.execute(
        select(TemplateField).where(TemplateField.template_id == template_id)
        .order_by(TemplateField.display_order, TemplateField.id)
    )
    return {
        "template_id": t.id,
        "version": t.version,
        "pages": [
            {"page_index": p.page_index, "width": p.image_width,
             "height": p.image_height}
            for p in pr.scalars().all()
        ],
        "fields": [
            {"name": f.field_name, "page_index": f.page_index,
             "strategy": f.strategy, "config": f.config,
             "post_process": f.post_process, "required": f.required,
             "display_order": f.display_order}
            for f in fr.scalars().all()
        ],
    }
