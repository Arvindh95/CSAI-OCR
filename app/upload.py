import hashlib
import json as _json

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


def parse_page_indexes(raw: str | None, n_files: int) -> list[int]:
    """Validate the optional page_indexes form field.

    Default (raw is None / empty) = list(range(n_files)) — i.e. upload
    order. When provided, must be a JSON array of unique non-negative
    integers, exactly n_files long.
    """
    if not raw:
        return list(range(n_files))
    try:
        parsed = _json.loads(raw)
    except _json.JSONDecodeError as e:
        raise BadRequest(f"page_indexes is not valid JSON: {e}")
    if not isinstance(parsed, list):
        raise BadRequest("page_indexes must be a JSON array")
    if len(parsed) != n_files:
        raise BadRequest(
            f"page_indexes length {len(parsed)} != file count {n_files}",
            detail={"page_indexes_len": len(parsed), "file_count": n_files},
        )
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in parsed):
        raise BadRequest("page_indexes must contain only integers")
    if any(x < 0 for x in parsed):
        raise BadRequest("page_indexes must be >= 0")
    if len(set(parsed)) != len(parsed):
        raise BadRequest("page_indexes must be unique (no duplicates)")
    return parsed
