from uuid import uuid4

import fakeredis.aioredis
import pytest
import pytest_asyncio

from app.billing.idempotency import TTL_SECONDS, check_and_store, idem_key, lookup


@pytest_asyncio.fixture
async def r():
    client = fakeredis.aioredis.FakeRedis()
    yield client
    await client.aclose()


@pytest.mark.asyncio
async def test_first_call_is_new(r):
    status, job_id = await check_and_store(r, 1, "k1", b"\x01" * 32, uuid4())
    assert status == "new"
    assert job_id is not None


@pytest.mark.asyncio
async def test_replay_same_body_returns_same_job_id(r):
    body = b"\x02" * 32
    original_job = uuid4()
    await check_and_store(r, 1, "k1", body, original_job)
    status, job_id = await check_and_store(r, 1, "k1", body, uuid4())
    assert status == "replay"
    assert job_id == original_job


@pytest.mark.asyncio
async def test_conflict_different_body(r):
    first_job = uuid4()
    await check_and_store(r, 1, "k1", b"\x03" * 32, first_job)
    status, job_id = await check_and_store(r, 1, "k1", b"\x04" * 32, uuid4())
    assert status == "conflict"
    assert job_id == first_job


@pytest.mark.asyncio
async def test_different_clients_isolated(r):
    body = b"\x05" * 32
    j1 = uuid4()
    j2 = uuid4()
    await check_and_store(r, 1, "k1", body, j1)
    status, job_id = await check_and_store(r, 2, "k1", body, j2)
    assert status == "new"
    assert job_id == j2


@pytest.mark.asyncio
async def test_ttl_set_to_24h(r):
    await check_and_store(r, 1, "k1", b"\x06" * 32, uuid4())
    ttl = await r.ttl(idem_key(1, "k1"))
    assert 0 < ttl <= TTL_SECONDS


@pytest.mark.asyncio
async def test_lookup_miss(r):
    assert await lookup(r, 1, "nope") is None


@pytest.mark.asyncio
async def test_lookup_hit(r):
    job = uuid4()
    await check_and_store(r, 1, "k1", b"\x07" * 32, job)
    entry = await lookup(r, 1, "k1")
    assert entry["job_id"] == str(job)
