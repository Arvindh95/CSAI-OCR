from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    max_transactions: int = Field(default=2000, ge=0)
    max_pages_per_txn: int = Field(default=1, ge=1)
    reset_period: str = Field(default="monthly", pattern="^(monthly|lifetime)$")


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    is_active: bool | None = None


class PlanUpsert(BaseModel):
    max_transactions: int = Field(ge=0)
    max_pages_per_txn: int = Field(default=1, ge=1)
    reset_period: str = Field(default="monthly", pattern="^(monthly|lifetime)$")


class ClientOut(BaseModel):
    id: int
    name: str
    email: str
    api_key_prefix: str
    is_active: bool
    created_at: datetime


class ClientCreated(ClientOut):
    api_key: str


class PlanOut(BaseModel):
    max_transactions: int
    max_pages_per_txn: int
    reset_period: str
    effective_from: datetime
    effective_to: datetime | None


class UsageOut(BaseModel):
    period_id: int | None
    period_start: datetime | None
    period_end: datetime | None
    used: int
    limit: int
    remaining: int


class JobOut(BaseModel):
    job_id: str
    endpoint: str
    status: str
    pages_submitted: int
    queued_at: datetime
    completed_at: datetime | None
    error_msg: str | None
