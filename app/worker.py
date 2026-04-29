import asyncio
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.billing.jobs import mark_done, mark_failed, mark_started
from app.billing.models import Job, UsageLog
from app.billing.quota import release
from app.billing.redis_client import get_redis
from app.metrics import jobs_total, ocr_duration_seconds
from app.ocr import extract_lines
from app.templates.extractor import extract_with_template
from app.templates.resolver import load_template_dict


def _normalize(s: str | None) -> str:
    if s is None:
        return ""
    s = s.strip().lower()
    s = re.sub(r"[\s:：\-–—.,;]+", "", s)
    return s


def _verify_fields(extracted: dict, expected: dict) -> dict:
    errors = extracted.pop("_errors", [])
    results = {}
    all_match = True
    for field_name, expected_val in expected.items():
        extracted_val = extracted.get(field_name)
        norm_expected = _normalize(str(expected_val))
        norm_extracted = _normalize(str(extracted_val) if extracted_val else "")
        match = norm_expected == norm_extracted
        if not match:
            all_match = False
        results[field_name] = {
            "expected": expected_val,
            "extracted": extracted_val,
            "match": match,
        }
    return {
        "verified": all_match,
        "fields": results,
        "all_extracted": {k: v for k, v in extracted.items()},
        "extraction_errors": errors if errors else None,
    }

load_dotenv("/opt/ocr-saas/.env")
logger = logging.getLogger("csai.worker")

_engine = None


def ocr_engine():
    global _engine
    if _engine is None:
        os.environ["FLAGS_use_mkldnn"] = "0"
        from paddleocr import PaddleOCR
        _engine = PaddleOCR(use_doc_orientation_classify=False,
                            use_doc_unwarping=False,
                            use_textline_orientation=False,
                            enable_mkldnn=False)
    return _engine


def _run_paddle(path: str) -> list[dict]:
    return extract_lines(ocr_engine(), path)


async def _process(job_id: UUID, endpoint: str, storage_path: str,
                   client_id: int, period_id: int,
                   template_id: int | None = None):
    db_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(db_url, poolclass=NullPool,
                                  connect_args={"ssl": False})
    Session = async_sessionmaker(engine, expire_on_commit=False)
    t0 = time.monotonic()
    try:
        async with Session() as s:
            await mark_started(s, job_id)
            await s.commit()

        template_dict = None
        if template_id is not None:
            async with Session() as s:
                template_dict = await load_template_dict(s, template_id)

        # Load input_meta: storage_paths list (multi-page),
        # page_indexes mapping, verify expected_fields.
        storage_paths: list[str] = [storage_path]
        page_idx_list: list[int] | None = None
        expected_fields = None
        async with Session() as s:
            from sqlalchemy import select
            row = (await s.execute(
                select(Job.input_meta).where(Job.id == job_id)
            )).scalar_one_or_none()
            if row:
                if row.get("storage_paths"):
                    storage_paths = list(row["storage_paths"])
                if row.get("page_indexes"):
                    page_idx_list = list(row["page_indexes"])
                if endpoint == "/api/v1/verify":
                    expected_fields = row.get("expected_fields")
        if page_idx_list is None or len(page_idx_list) != len(storage_paths):
            page_idx_list = list(range(len(storage_paths)))

        # Resize each uploaded page to match its declared template page
        # dims so OCR coords align with annotated zone coordinates.
        if template_dict is not None:
            _pages = template_dict.get("pages", [])
            _pages_by_idx = {p["page_index"]: p for p in _pages}
            for sp, pi in zip(storage_paths, page_idx_list):
                target = _pages_by_idx.get(pi)
                if not target:
                    continue
                try:
                    from PIL import Image
                    img = Image.open(sp)
                    img.load()
                    tw, th = target["width"], target["height"]
                    if img.size != (tw, th):
                        img = img.convert("RGB").resize((tw, th), Image.LANCZOS)
                        img.save(sp, quality=95)
                except Exception:
                    pass

        try:
            lines = []
            for sp, pi in zip(storage_paths, page_idx_list):
                page_lines = await asyncio.get_event_loop().run_in_executor(
                    None, _run_paddle, sp
                )
                for ln in page_lines:
                    ln["page_index"] = pi
                lines.extend(page_lines)
            if template_dict is not None:
                fields = extract_with_template(lines, template_dict)

                if expected_fields:
                    verify_result = _verify_fields(fields, expected_fields)
                    result = {
                        "lines": lines,
                        "template_id": template_dict["template_id"],
                        "template_version": template_dict["version"],
                        **verify_result,
                    }
                else:
                    result = {
                        "lines": lines,
                        "fields": fields,
                        "template_id": template_dict["template_id"],
                        "template_version": template_dict["version"],
                    }
            else:
                result = {
                    "lines": lines,
                    "joined": "\n".join(ln["text"] for ln in lines),
                }
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

        elapsed = time.monotonic() - t0
        ocr_duration_seconds.labels(status=status).observe(elapsed)
        jobs_total.labels(status=status, endpoint=endpoint).inc()
    finally:
        await engine.dispose()
        for sp in storage_paths if 'storage_paths' in locals() else [storage_path]:
            try:
                Path(sp).unlink(missing_ok=True)
            except Exception:
                pass


def run_ocr_job(job_id_str: str, endpoint: str, storage_path: str,
                client_id: int, period_id: int,
                template_id: int | None = None):
    asyncio.run(_process(UUID(job_id_str), endpoint, storage_path,
                         client_id, period_id, template_id))
