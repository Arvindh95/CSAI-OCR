from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.models import Period, Plan

LIFETIME_END = datetime(9999, 1, 1, tzinfo=timezone.utc)


def month_window(now: datetime) -> tuple[datetime, datetime]:
    now = now.astimezone(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def lifetime_window(plan_effective_from: datetime) -> tuple[datetime, datetime]:
    return plan_effective_from.astimezone(timezone.utc), LIFETIME_END


def window_for_plan(plan: Plan, now: datetime) -> tuple[datetime, datetime]:
    if plan.reset_period == "monthly":
        return month_window(now)
    return lifetime_window(plan.effective_from)


async def current_plan(session: AsyncSession, client_id: int) -> Plan | None:
    result = await session.execute(
        select(Plan).where(Plan.client_id == client_id, Plan.effective_to.is_(None))
    )
    return result.scalar_one_or_none()


async def get_or_create_open_period(
    session: AsyncSession, client_id: int, now: datetime | None = None
) -> Period:
    now = now or datetime.now(timezone.utc)
    plan = await current_plan(session, client_id)
    if plan is None:
        raise LookupError(f"no active plan for client {client_id}")
    start, end = window_for_plan(plan, now)
    result = await session.execute(
        select(Period).where(
            Period.client_id == client_id,
            Period.period_start == start,
            Period.period_end == end,
            Period.is_open.is_(True),
        )
    )
    period = result.scalar_one_or_none()
    if period is not None:
        return period
    period = Period(
        client_id=client_id, period_start=start, period_end=end, is_open=True
    )
    session.add(period)
    await session.flush()
    return period
