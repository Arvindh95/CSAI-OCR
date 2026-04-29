import hashlib

import magic

from app.errors import BadRequest, PayloadTooLarge, UnsupportedMedia

MAX_BYTES = 10 * 1024 * 1024
ALLOWED_MIME = {"image/jpeg", "image/png", "image/tiff"}


def _sniff_mime(data: bytes) -> str:
    return magic.from_buffer(data[:4096], mime=True)


def validate_upload(data: bytes, max_pages: int = 1) -> tuple[str, int, bytes]:
    if not data:
        raise BadRequest("empty body")
    if len(data) > MAX_BYTES:
        raise PayloadTooLarge(f"max {MAX_BYTES} bytes")
    mime = _sniff_mime(data)
    if mime not in ALLOWED_MIME:
        raise UnsupportedMedia(f"got {mime}", detail={"mime": mime})
    pages = 1
    if pages > max_pages:
        raise BadRequest(
            f"too many pages: {pages} > plan limit {max_pages}",
            detail={"pages": pages, "max_pages": max_pages},
        )
    body_hash = hashlib.sha256(data).digest()
    return mime, pages, body_hash
