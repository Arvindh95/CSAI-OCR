import json
from uuid import UUID

from redis.asyncio import Redis

TTL_SECONDS = 604800


def idem_key(client_id: int, key: str) -> str:
    return f"idem:{client_id}:{key}"


async def check_and_store(
    r: Redis, client_id: int, key: str, body_hash: bytes, job_id: UUID
) -> tuple[str, UUID | None]:
    rkey = idem_key(client_id, key)
    payload = json.dumps({"body_hash": body_hash.hex(), "job_id": str(job_id)})
    existing_raw = await r.set(rkey, payload, ex=TTL_SECONDS, nx=True, get=True)
    if existing_raw is None:
        return "new", job_id
    if isinstance(existing_raw, bytes):
        existing_raw = existing_raw.decode()
    existing = json.loads(existing_raw)
    if existing["body_hash"] == body_hash.hex():
        return "replay", UUID(existing["job_id"])
    return "conflict", UUID(existing["job_id"])


async def lookup(r: Redis, client_id: int, key: str) -> dict | None:
    raw = await r.get(idem_key(client_id, key))
    if raw is None:
        return None
    return json.loads(raw)


async def discard(r: Redis, client_id: int, key: str, job_id: UUID) -> None:
    """Delete idempotency record only if it still points to *this* job_id.

    Avoids racing a concurrent winner that already claimed the same key
    with a different job_id.
    """
    rkey = idem_key(client_id, key)
    raw = await r.get(rkey)
    if raw is None:
        return
    if isinstance(raw, bytes):
        raw = raw.decode()
    try:
        existing = json.loads(raw)
    except ValueError:
        return
    if existing.get("job_id") == str(job_id):
        await r.delete(rkey)
