from app.billing.auth import (
    KEY_PREFIX,
    generate_api_key,
    hash_api_key,
    key_prefix,
)


def test_generated_key_shape():
    k = generate_api_key()
    assert k.startswith(KEY_PREFIX)
    assert len(k) == len(KEY_PREFIX) + 32


def test_generated_keys_are_unique():
    assert generate_api_key() != generate_api_key()


def test_hash_is_deterministic():
    raw = "ocr_live_" + "a" * 32
    assert hash_api_key(raw) == hash_api_key(raw)


def test_hash_changes_with_input():
    a = "ocr_live_" + "a" * 32
    b = "ocr_live_" + "b" * 32
    assert hash_api_key(a) != hash_api_key(b)


def test_hash_is_32_bytes_sha256():
    assert len(hash_api_key("ocr_live_" + "a" * 32)) == 32


def test_prefix_length():
    raw = generate_api_key()
    assert len(key_prefix(raw)) == 12
    assert key_prefix(raw) == raw[:12]
