from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FieldDef(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    page_index: int = Field(default=0, ge=0)
    strategy: str = Field(pattern="^(anchor|zone|regex|between)$")
    config: dict[str, Any]
    post_process: str | None = None
    required: bool = False
    display_order: int = 0


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    doc_type_code: str = Field(min_length=1, max_length=100,
                                pattern=r"^[a-z0-9_\-]+$")
    client_id: int | None = None
    fields: list[FieldDef] = Field(default_factory=list)


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    fields: list[FieldDef] | None = None


class PageOut(BaseModel):
    page_index: int
    image_path: str
    image_width: int
    image_height: int


class FieldOut(FieldDef):
    id: int


class TemplateOut(BaseModel):
    id: int
    client_id: int | None
    name: str
    doc_type_code: str
    version: int
    is_active: bool
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    pages: list[PageOut] = []
    fields: list[FieldOut] = []


class TemplateListItem(BaseModel):
    id: int
    client_id: int | None
    name: str
    doc_type_code: str
    version: int
    is_active: bool
    created_at: datetime


class GrantIn(BaseModel):
    template_id: int


class GrantOut(BaseModel):
    client_id: int
    template_id: int
    granted_at: datetime


class TestResult(BaseModel):
    lines: list[dict]
    extracted: dict
