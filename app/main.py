import logging
import logging.config
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from prometheus_fastapi_instrumentator import Instrumentator

from app.errors import install_handlers
from app.logging_mw import AccessLogMiddleware
from app.metrics import queue_depth
from app.routers import admin, admin_templates, health, ocr

_LOG_CFG = os.environ.get("LOG_CONFIG", "/opt/ocr-saas/config/logging.json")
if os.path.exists(_LOG_CFG):
    import json
    with open(_LOG_CFG) as f:
        logging.config.dictConfig(json.load(f))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.getLogger("csai").info("startup")
    yield
    logging.getLogger("csai").info("shutdown")


app = FastAPI(title="CSAI-OCR", version="2.0.0", lifespan=lifespan)
app.add_middleware(AccessLogMiddleware)
install_handlers(app)

Instrumentator(
    should_group_status_codes=True,
    excluded_handlers=["/metrics", "/health"],
).instrument(app)


@app.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    try:
        from app.queue import get_queue
        q = get_queue()
        queue_depth.labels(queue=q.name).set(q.count)
    except Exception:
        pass
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(health.router)
app.include_router(ocr.router)
app.include_router(admin.router)
app.include_router(admin_templates.router)
