import os

from dotenv import load_dotenv
from redis.asyncio import Redis, from_url

load_dotenv("/opt/ocr-saas/.env")

REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")


def get_redis() -> Redis:
    return from_url(REDIS_URL, decode_responses=False)
