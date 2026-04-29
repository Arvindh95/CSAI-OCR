import hashlib

import pytest

from app.errors import BadRequest, PayloadTooLarge, UnsupportedMedia
from app.upload import MAX_BYTES, validate_upload


PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c636000010000000500010d0a2db40000000049454e"
    "44ae426082"
)


def test_rejects_empty():
    with pytest.raises(BadRequest):
        validate_upload(b"")


def test_rejects_too_large():
    with pytest.raises(PayloadTooLarge):
        validate_upload(b"\x00" * (MAX_BYTES + 1))


def test_rejects_unknown_mime():
    with pytest.raises(UnsupportedMedia):
        validate_upload(b"this is plain text, not an image" * 10)


def test_accepts_png():
    mime, pages, body_hash = validate_upload(PNG_1X1)
    assert mime == "image/png"
    assert pages == 1
    assert body_hash == hashlib.sha256(PNG_1X1).digest()


def test_rejects_pdf_now_unsupported():
    with pytest.raises(UnsupportedMedia):
        validate_upload(b"%PDF-1.4 not really")
