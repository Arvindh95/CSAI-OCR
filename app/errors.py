import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError

_LOG = logging.getLogger("csai.errors")

# Postgres SQLSTATE → (http_status, error_code). Messages fall back to the
# Postgres DETAIL string, which already names the offending column/value,
# e.g. "Key (template_id, field_name)=(54, nama_perniagaan) already exists."
_PG_STATE = {
    "23505": (409, "unique_conflict"),
    "23503": (400, "foreign_key_violation"),
    "23502": (400, "null_violation"),
    "23514": (400, "check_violation"),
    "23P01": (400, "exclusion_violation"),
}


class APIError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str = "", detail: dict | None = None):
        self.message = message or self.code
        self.detail = detail or {}


class AuthError(APIError):
    status_code = 401
    code = "unauthorized"


class PayloadTooLarge(APIError):
    status_code = 413
    code = "payload_too_large"


class UnsupportedMedia(APIError):
    status_code = 415
    code = "unsupported_media_type"


class QuotaExceeded(APIError):
    status_code = 429
    code = "quota_exceeded"


class IdempotencyConflict(APIError):
    status_code = 409
    code = "idempotency_conflict"


class NotFound(APIError):
    status_code = 404
    code = "not_found"


class BadRequest(APIError):
    status_code = 400
    code = "bad_request"


class Forbidden(APIError):
    status_code = 403
    code = "forbidden"


def _payload(code: str, message: str, request_id: str | None, detail: dict | None = None) -> dict:
    body = {"error": {"code": code, "message": message}}
    if request_id:
        body["error"]["request_id"] = request_id
    if detail:
        body["error"]["detail"] = detail
    return body


def _integrity_to_payload(exc: IntegrityError) -> tuple[int, str, str, dict]:
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None)
    detail_text = (getattr(orig, "detail", None) or "").strip()
    constraint = getattr(orig, "constraint_name", None)
    status, code = _PG_STATE.get(sqlstate, (500, "database_error"))
    message = detail_text or str(orig) or "database integrity error"
    extra: dict = {}
    if sqlstate:
        extra["sqlstate"] = sqlstate
    if constraint:
        extra["constraint"] = constraint
    return status, code, message, extra


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def _api_error(request: Request, exc: APIError):
        rid = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(exc.code, exc.message, rid, exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        rid = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=400,
            content=_payload("validation_error", "invalid request", rid,
                             {"errors": exc.errors()}),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError):
        rid = getattr(request.state, "request_id", None)
        status, code, message, detail = _integrity_to_payload(exc)
        if status >= 500:
            _LOG.exception("unmapped integrity error", extra={"request_id": rid})
        else:
            _LOG.info("db constraint violation: %s", message,
                      extra={"request_id": rid})
        return JSONResponse(
            status_code=status,
            content=_payload(code, message, rid, detail or None),
        )

    @app.exception_handler(OperationalError)
    async def _operational(request: Request, exc: OperationalError):
        rid = getattr(request.state, "request_id", None)
        _LOG.exception("db operational error", extra={"request_id": rid})
        return JSONResponse(
            status_code=503,
            content=_payload("database_unavailable",
                             "database is unreachable, try again shortly", rid),
        )

    @app.exception_handler(asyncio.TimeoutError)
    async def _timeout(request: Request, exc: asyncio.TimeoutError):
        rid = getattr(request.state, "request_id", None)
        _LOG.warning("request timed out", extra={"request_id": rid})
        return JSONResponse(
            status_code=504,
            content=_payload("timeout", "operation timed out", rid),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        rid = getattr(request.state, "request_id", None)
        _LOG.exception("unhandled exception", extra={"request_id": rid})
        # Expose the exception class + short message, not the full traceback,
        # so the client sees something actionable instead of a bare 500.
        ename = type(exc).__name__
        msg = str(exc).strip().splitlines()[0] if str(exc).strip() else ename
        if len(msg) > 300:
            msg = msg[:297] + "..."
        return JSONResponse(
            status_code=500,
            content=_payload("internal_error", f"{ename}: {msg}", rid),
        )
