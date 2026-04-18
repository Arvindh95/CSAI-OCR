import logging
import logging.config
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.errors import install_handlers
from app.logging_mw import AccessLogMiddleware
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

app.include_router(health.router)
app.include_router(ocr.router)
app.include_router(admin.router)
app.include_router(admin_templates.router)
