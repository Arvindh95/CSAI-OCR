import json
from uuid import UUID

from redis.asyncio import Redis

TTL_SECONDS = 86400


def idem_key(client_id: int, key: str) -> str:
    return f"idem:{client_id}:{key}"


async def check_and_store(
    r: Redis, client_id: int, key: str, body_hash: bytes, job_id: UUID
) -> tuple[str, UUID | None]:
    rkey = idem_key(client_id, key)
    payload = json.dumps({"body_hash": body_hash.hex(), "job_id": str(job_id)})
    stored = await r.set(rkey, payload, ex=TTL_SECONDS, nx=True)
    if stored:
        return "new", job_id
    existing_raw = await r.get(rkey)
    if existing_raw is None:
        await r.set(rkey, payload, ex=TTL_SECONDS)
        return "new", job_id
    existing = json.loads(existing_raw)
    if existing["body_hash"] == body_hash.hex():
        return "replay", UUID(existing["job_id"])
    return "conflict", UUID(existing["job_id"])


async def lookup(r: Redis, client_id: int, key: str) -> dict | None:
    raw = await r.get(idem_key(client_id, key))
    if raw is None:
        return None
    return json.loads(raw)
