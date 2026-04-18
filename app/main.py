import os
import tempfile
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.ocr import get_ocr, extract_lines
from app.parser import parse_ssm, verify_fields, check_expiry


# ── Startup: load OCR model once ─────────────────────────────
ocr_model = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global ocr_model
    print("[startup] Loading PaddleOCR model...")
    ocr_model = get_ocr()
    print("[startup] Model ready.")
    yield
    print("[shutdown] Done.")


# ── App ───────────────────────────────────────────────────────
app = FastAPI(
    title="SSM OCR API",
    description="PaddleOCR-powered SSM document extraction and verification",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Response models ───────────────────────────────────────────
class OCRResponse(BaseModel):
    lines: list[dict]
    fields: dict


class VerifyResponse(BaseModel):
    fields: dict
    verification: dict
    verified: bool


# ── Helpers ───────────────────────────────────────────────────
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}

async def save_upload(file: UploadFile) -> str:
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported file type: {ext}")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    tmp.write(await file.read())
    tmp.close()
    return tmp.name


# ── Routes ────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": ocr_model is not None}


@app.post("/ocr", response_model=OCRResponse)
async def ocr_extract(file: UploadFile = File(...)):
    """Extract all text + parsed fields from uploaded document."""
    tmp_path = await save_upload(file)
    try:
        lines = extract_lines(ocr_model, tmp_path)
        fields = parse_ssm(lines)
        fields["_expiry_check"] = check_expiry(fields)
        return {"lines": lines, "fields": fields}
    finally:
        os.unlink(tmp_path)


@app.post("/verify", response_model=VerifyResponse)
async def ocr_verify(
    file: UploadFile = File(...),
    name: str = Form(default=None),
    reg_no: str = Form(default=None),
):
    """Extract fields and verify against provided name/reg_no."""
    if not name and not reg_no:
        raise HTTPException(400, "Provide at least one of: name, reg_no")

    tmp_path = await save_upload(file)
    try:
        lines = extract_lines(ocr_model, tmp_path)
        fields = parse_ssm(lines)
        expiry_check = check_expiry(fields)
        fields["_expiry_check"] = expiry_check
        verification = verify_fields(fields, name, reg_no)
        verified = all(v["match"] for v in verification.values())
        return {"fields": fields, "verification": verification, "verified": verified}
    finally:
        os.unlink(tmp_path)
