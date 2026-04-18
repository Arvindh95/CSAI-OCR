from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


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

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        rid = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=500,
            content=_payload("internal_error", "internal server error", rid),
        )
