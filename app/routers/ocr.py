import hashlib
import ipaddress
import os
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.idempotency import check_and_store, discard as discard_idem
from app.billing.jobs import create_job, get_job, mark_failed
from app.billing.models import Client
from app.billing.periods import current_plan, get_or_create_open_period
from app.billing.quota import release, reserve
from app.deps import current_client, get_redis_dep, get_session
from app.errors import BadRequest, IdempotencyConflict, NotFound, QuotaExceeded
from app.metrics import (
    idempotency_conflicts_total,
    jobs_submitted_total,
    quota_denies_total,
)
from app.queue import enqueue_ocr_job
from app.templates.resolver import resolve_for_client
from app.upload import parse_page_indexes, validate_upload

STORAGE_DIR = Path(os.environ.get("OCR_STORAGE_DIR", "/opt/ocr-saas/storage"))
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/api/v1")

_MIME_EXT = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/tiff": ".tif",
}


def _client_ip(request: Request) -> str | None:
    real = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for")
    if real:
        candidate = real.split(",")[0].strip()
    elif request.client:
        candidate = request.client.host
    else:
        return None
    try:
        ipaddress.ip_address(candidate)
        return candidate
    except ValueError:
        return None


@router.post("/ocr", status_code=202)
async def submit_ocr(
    request: Request,
    file: UploadFile | None = File(default=None),
    files: list[UploadFile] = File(default=[]),
    doc_type: str | None = Form(default=None),
    page_indexes: str | None = Form(
        default=None,
        description='Optional JSON array mapping each uploaded file to its '
                    'logical page index, e.g. "[1,0,2]". Length must equal '
                    'file count; values must be unique non-negative ints. '
                    'Defaults to upload order ([0,1,...]).',
    ),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    client: Client = Depends(current_client),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis_dep),
):
    upload_files: list[UploadFile] = []
    if files:
        upload_files.extend(files)
    if file is not None:
        upload_files.append(file)
    if not upload_files:
        raise BadRequest("no file uploaded")

    plan = await current_plan(session, client.id)
    if plan is None:
        raise BadRequest("no active plan for client")
    if len(upload_files) > plan.max_pages_per_txn:
        raise BadRequest(
            f"too many pages: {len(upload_files)} > plan limit {plan.max_pages_per_txn}",
            detail={"pages": len(upload_files), "max_pages": plan.max_pages_per_txn},
        )

    file_records: list[dict] = []
    per_file_hashes: list[bytes] = []
    for uf in upload_files:
        data = await uf.read()
        mime, _pg, fhash = validate_upload(data, max_pages=plan.max_pages_per_txn)
        file_records.append({"data": data, "mime": mime, "filename": uf.filename})
        per_file_hashes.append(fhash)
    pages = len(file_records)
    body_hash = hashlib.sha256(b"".join(per_file_hashes)).digest()
    page_idx_list = parse_page_indexes(page_indexes, pages)

    template = None
    if doc_type:
        template = await resolve_for_client(session, client.id, doc_type)

    period = await get_or_create_open_period(session, client.id)
    await session.commit()

    job_id = uuid4()
    if idempotency_key:
        status, existing_id = await check_and_store(
            redis, client.id, idempotency_key, body_hash, job_id
        )
        if status == "conflict":
            idempotency_conflicts_total.inc()
            raise IdempotencyConflict(
                "idempotency-key reused with different body",
                detail={"job_id": str(existing_id)},
            )
        if status == "replay":
            fetched = await get_job(session, client.id, existing_id)
            return {
                "job_id": str(existing_id),
                "status": fetched.status if fetched else "queued",
                "replay": True,
            }

    if not await reserve(redis, client.id, period.id, limit=plan.max_transactions):
        quota_denies_total.inc()
        if idempotency_key:
            await discard_idem(redis, client.id, idempotency_key, job_id)
        raise QuotaExceeded(f"plan limit {plan.max_transactions} reached this period")

    storage_paths: list[Path] = [
        STORAGE_DIR / f"{job_id}_p{i}{_MIME_EXT[rec['mime']]}"
        for i, rec in enumerate(file_records)
    ]
    primary_path = storage_paths[0]
    primary_mime = file_records[0]["mime"]

    try:
        await create_job(
            session, client.id, period.id, endpoint="/api/v1/ocr",
            pages=pages, idempotency_key=idempotency_key, body_hash=body_hash,
            input_meta={
                "mime": primary_mime,
                "filename": file_records[0]["filename"],
                "doc_type": doc_type,
                "storage_paths": [str(p) for p in storage_paths],
                "filenames": [r["filename"] for r in file_records],
                "mimes": [r["mime"] for r in file_records],
                "page_indexes": page_idx_list,
            },
            ip_address=_client_ip(request),
            job_id=job_id,
            template_id=template.id if template else None,
            template_version=template.version if template else None,
        )
        for sp, rec in zip(storage_paths, file_records):
            sp.write_bytes(rec["data"])
        await session.commit()
    except Exception:
        await session.rollback()
        await release(redis, client.id, period.id)
        for sp in storage_paths:
            try:
                sp.unlink(missing_ok=True)
            except OSError:
                pass
        if idempotency_key:
            await discard_idem(redis, client.id, idempotency_key, job_id)
        raise

    try:
        enqueue_ocr_job(
            job_id, "/api/v1/ocr", str(primary_path), client.id, period.id,
            template_id=template.id if template else None,
        )
    except Exception:
        try:
            await mark_failed(session, job_id, "enqueue failed")
            await session.commit()
        except Exception:
            await session.rollback()
        await release(redis, client.id, period.id)
        for sp in storage_paths:
            try:
                sp.unlink(missing_ok=True)
            except OSError:
                pass
        if idempotency_key:
            await discard_idem(redis, client.id, idempotency_key, job_id)
        raise

    jobs_submitted_total.labels(
        template=(doc_type or "none"), mime=primary_mime,
    ).inc()
    return {"job_id": str(job_id), "status": "queued"}


@router.get("/jobs/{job_id}")
async def job_status(
    job_id: UUID,
    client: Client = Depends(current_client),
    session: AsyncSession = Depends(get_session),
):
    job = await get_job(session, client.id, job_id)
    if job is None:
        raise NotFound(f"job {job_id} not found")
    body = {
        "job_id": str(job.id),
        "status": job.status,
        "pages_submitted": job.pages_submitted,
        "queued_at": job.queued_at.isoformat(),
    }
    if job.status == "done":
        body["result"] = job.result
        body["completed_at"] = job.completed_at.isoformat() if job.completed_at else None
    elif job.status == "failed":
        body["error"] = job.error_msg
    return body
