import hashlib
import hmac
import os
import secrets

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.models import Client

load_dotenv("/opt/ocr-saas/.env")

_PEPPER = os.environ["API_KEY_PEPPER"].encode()
KEY_PREFIX = "ocr_live_"
PREFIX_DISPLAY_LEN = 12


def generate_api_key() -> str:
    return KEY_PREFIX + secrets.token_hex(16)


def hash_api_key(raw: str) -> bytes:
    return hashlib.sha256(_PEPPER + raw.encode()).digest()


def key_prefix(raw: str) -> str:
    return raw[:PREFIX_DISPLAY_LEN]


async def authenticate(session: AsyncSession, raw_key: str) -> Client | None:
    if not raw_key or not raw_key.startswith(KEY_PREFIX):
        return None
    candidate = hash_api_key(raw_key)
    result = await session.execute(
        select(Client).where(Client.api_key_hash == candidate, Client.is_active.is_(True))
    )
    client = result.scalar_one_or_none()
    if client is None:
        return None
    if not hmac.compare_digest(client.api_key_hash, candidate):
        return None
    return client
