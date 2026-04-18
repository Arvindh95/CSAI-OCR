from redis.asyncio import Redis


def quota_key(client_id: int, period_id: int) -> str:
    return f"quota:{client_id}:{period_id}"


async def reserve(r: Redis, client_id: int, period_id: int, limit: int, ttl: int = 2678400) -> bool:
    key = quota_key(client_id, period_id)
    new_count = await r.incr(key)
    if new_count == 1:
        await r.expire(key, ttl)
    if new_count > limit:
        await r.decr(key)
        return False
    return True


async def release(r: Redis, client_id: int, period_id: int) -> int:
    key = quota_key(client_id, period_id)
    val = await r.decr(key)
    if val < 0:
        await r.set(key, 0)
        return 0
    return val


async def current(r: Redis, client_id: int, period_id: int) -> int:
    val = await r.get(quota_key(client_id, period_id))
    return int(val) if val is not None else 0


async def reset(r: Redis, client_id: int, period_id: int, value: int = 0) -> None:
    await r.set(quota_key(client_id, period_id), value)
