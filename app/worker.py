import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.billing.jobs import mark_done, mark_failed, mark_started
from app.billing.models import UsageLog
from app.billing.quota import release
from app.billing.redis_client import get_redis

load_dotenv("/opt/ocr-saas/.env")
logger = logging.getLogger("csai.worker")

_engine = None


def ocr_engine():
    global _engine
    if _engine is None:
        from paddleocr import PaddleOCR
        _engine = PaddleOCR(use_doc_orientation_classify=False,
                            use_doc_unwarping=False, use_textline_orientation=False)
    return _engine


def _run_paddle(path: str) -> dict:
    ocr = ocr_engine()
    result = ocr.predict(path)
    texts = []
    for page in result:
        if hasattr(page, "json"):
            data = page.json
            for t in data.get("rec_texts", []):
                texts.append(t)
    return {"text_lines": texts, "joined": "\n".join(texts)}


async def _process(job_id: UUID, storage_path: str, client_id: int, period_id: int):
    db_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(db_url, poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as s:
            await mark_started(s, job_id)
            await s.commit()
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, _run_paddle, storage_path
            )
            status = "done"
            err = None
        except Exception as e:
            logger.exception("ocr failed job=%s", job_id)
            status = "failed"
            err = str(e)[:500]
            result = None
        async with Session() as s:
            if status == "done":
                await mark_done(s, job_id, result)
                s.add(UsageLog(
                    client_id=client_id, period_id=period_id, job_id=job_id,
                    pages=1, status="success",
                    timestamp=datetime.now(timezone.utc),
                ))
            else:
                await mark_failed(s, job_id, err)
                r = get_redis()
                await release(r, client_id, period_id)
                await r.aclose()
                s.add(UsageLog(
                    client_id=client_id, period_id=period_id, job_id=job_id,
                    pages=1, status="error", reject_reason=err[:200],
                    timestamp=datetime.now(timezone.utc),
                ))
            await s.commit()
    finally:
        await engine.dispose()
        try:
            Path(storage_path).unlink(missing_ok=True)
        except Exception:
            pass


def run_ocr_job(job_id_str: str, endpoint: str, storage_path: str,
                client_id: int, period_id: int):
    asyncio.run(_process(UUID(job_id_str), storage_path, client_id, period_id))
