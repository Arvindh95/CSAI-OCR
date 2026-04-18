import asyncio

import fakeredis.aioredis
import pytest
import pytest_asyncio

from app.billing.quota import current, release, reserve, reset


@pytest_asyncio.fixture
async def r():
    client = fakeredis.aioredis.FakeRedis()
    yield client
    await client.aclose()


@pytest.mark.asyncio
async def test_reserve_under_limit(r):
    assert await reserve(r, 1, 100, limit=5) is True
    assert await current(r, 1, 100) == 1


@pytest.mark.asyncio
async def test_reserve_at_limit(r):
    for _ in range(5):
        assert await reserve(r, 1, 100, limit=5) is True
    assert await reserve(r, 1, 100, limit=5) is False
    assert await current(r, 1, 100) == 5


@pytest.mark.asyncio
async def test_release_decrements(r):
    await reserve(r, 1, 100, limit=5)
    await reserve(r, 1, 100, limit=5)
    await release(r, 1, 100)
    assert await current(r, 1, 100) == 1


@pytest.mark.asyncio
async def test_release_never_negative(r):
    await release(r, 1, 100)
    assert await current(r, 1, 100) == 0


@pytest.mark.asyncio
async def test_burst_race_50_parallel_5_slots(r):
    results = await asyncio.gather(
        *[reserve(r, 1, 100, limit=5) for _ in range(50)]
    )
    assert sum(results) == 5
    assert await current(r, 1, 100) == 5


@pytest.mark.asyncio
async def test_reset_clears(r):
    await reserve(r, 1, 100, limit=5)
    await reset(r, 1, 100)
    assert await current(r, 1, 100) == 0


@pytest.mark.asyncio
async def test_different_periods_isolated(r):
    await reserve(r, 1, 100, limit=5)
    await reserve(r, 1, 100, limit=5)
    assert await current(r, 1, 101) == 0
    assert await current(r, 2, 100) == 0
