import hashlib

import pytest

from app.errors import BadRequest, PayloadTooLarge, UnsupportedMedia
from app.upload import MAX_BYTES, parse_page_indexes, validate_upload


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


def test_page_indexes_default_when_omitted():
    assert parse_page_indexes(None, 3) == [0, 1, 2]
    assert parse_page_indexes("", 2) == [0, 1]


def test_page_indexes_explicit_order():
    assert parse_page_indexes("[1,0,2]", 3) == [1, 0, 2]


def test_page_indexes_sparse_allowed():
    assert parse_page_indexes("[0,2,5]", 3) == [0, 2, 5]


def test_page_indexes_rejects_bad_json():
    with pytest.raises(BadRequest):
        parse_page_indexes("not json", 1)


def test_page_indexes_rejects_non_array():
    with pytest.raises(BadRequest):
        parse_page_indexes('{"a":1}', 1)


def test_page_indexes_rejects_length_mismatch():
    with pytest.raises(BadRequest):
        parse_page_indexes("[0,1]", 3)


def test_page_indexes_rejects_negative():
    with pytest.raises(BadRequest):
        parse_page_indexes("[0,-1,2]", 3)


def test_page_indexes_rejects_duplicates():
    with pytest.raises(BadRequest):
        parse_page_indexes("[0,0,1]", 3)


def test_page_indexes_rejects_non_int():
    with pytest.raises(BadRequest):
        parse_page_indexes('["0","1"]', 2)
    with pytest.raises(BadRequest):
        parse_page_indexes("[true,false]", 2)
