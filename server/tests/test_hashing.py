"""Tests for content hashing (Plan 1.02)."""
from __future__ import annotations

from server.config_collector.hashing import sha256_canonical


def test_sha256_returns_hex_string():
    """Result is a 64-char lowercase hex string."""
    h = sha256_canonical({"a": 1})
    assert isinstance(h, str)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_sha256_deterministic_for_same_payload():
    """Same semantic payload in different key order → same hash."""
    a = {"z": 1, "a": 2, "nested": {"y": 1, "x": 2}}
    b = {"a": 2, "z": 1, "nested": {"x": 2, "y": 1}}
    assert sha256_canonical(a) == sha256_canonical(b)


def test_sha256_different_for_different_payloads():
    assert sha256_canonical({"a": 1}) != sha256_canonical({"a": 2})
    assert sha256_canonical([1, 2, 3]) != sha256_canonical([1, 2, 4])
    # Order-sensitive for arrays
    assert sha256_canonical([1, 2, 3]) != sha256_canonical([3, 2, 1])


def test_sha256_empty_object_is_stable():
    # Known SHA-256 of '{}' (canonical form of empty dict)
    assert sha256_canonical({}) == "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"


from server.config_collector.hashing import canonical_payload


def test_canonical_payload_returns_hash_payload_and_size():
    payload, hash_hex, byte_size = canonical_payload({"a": 1, "b": [1, 2]})
    assert payload == '{"a":1,"b":[1,2]}'
    assert len(hash_hex) == 64
    assert byte_size == len(payload.encode("utf-8"))


def test_canonical_payload_unicode_byte_size():
    """Byte size reflects UTF-8 encoding, not char count."""
    payload, _, byte_size = canonical_payload({"name": "café"})
    # 'café' is 4 characters but 5 bytes in UTF-8 (é = 2 bytes)
    assert byte_size == len(payload.encode("utf-8"))
    assert byte_size > len(payload)  # because of multi-byte char
