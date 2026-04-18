import hashlib
import io

import magic

from app.errors import BadRequest, PayloadTooLarge, UnsupportedMedia

MAX_BYTES = 10 * 1024 * 1024
ALLOWED_MIME = {"image/jpeg", "image/png", "image/tiff", "application/pdf"}


def _sniff_mime(data: bytes) -> str:
    return magic.from_buffer(data[:4096], mime=True)


def _count_pdf_pages(data: bytes) -> int:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise BadRequest("pdf support unavailable") from e
    try:
        reader = PdfReader(io.BytesIO(data))
        return len(reader.pages)
    except Exception as e:
        raise BadRequest("corrupt pdf") from e


def validate_upload(data: bytes, max_pages: int = 1) -> tuple[str, int, bytes]:
    if not data:
        raise BadRequest("empty body")
    if len(data) > MAX_BYTES:
        raise PayloadTooLarge(f"max {MAX_BYTES} bytes")
    mime = _sniff_mime(data)
    if mime not in ALLOWED_MIME:
        raise UnsupportedMedia(f"got {mime}", detail={"mime": mime})
    pages = _count_pdf_pages(data) if mime == "application/pdf" else 1
    if pages > max_pages:
        raise BadRequest(
            f"too many pages: {pages} > plan limit {max_pages}",
            detail={"pages": pages, "max_pages": max_pages},
        )
    body_hash = hashlib.sha256(data).digest()
    return mime, pages, body_hash
