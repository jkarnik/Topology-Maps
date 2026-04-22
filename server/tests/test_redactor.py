"""Tests for the redactor walker (Plan 1.03)."""
from __future__ import annotations

import pytest

from server.config_collector.redactor import parse_path, mask_path


def test_parse_simple_key():
    assert parse_path("foo") == [("key", "foo")]


def test_parse_nested_key():
    assert parse_path("foo.bar.baz") == [("key", "foo"), ("key", "bar"), ("key", "baz")]


def test_parse_array_wildcard():
    assert parse_path("foo[*].bar") == [("key", "foo"), ("array",), ("key", "bar")]


def test_parse_top_level_array():
    assert parse_path("[*].psk") == [("array",), ("key", "psk")]


def test_parse_array_of_arrays():
    assert parse_path("peers[*].secrets[*]") == [
        ("key", "peers"), ("array",), ("key", "secrets"), ("array",),
    ]


def test_parse_rejects_malformed():
    with pytest.raises(ValueError):
        parse_path("")
    with pytest.raises(ValueError):
        parse_path("foo[bar]")  # only [*] is supported


# Masking tests ---------------------------------------------------------------


def test_mask_top_level_key():
    payload = {"psk": "supersecret", "name": "Guest"}
    mask_path(payload, [("key", "psk")])
    assert payload["psk"] == {"_redacted": True, "_hash": _sha256("supersecret")}
    assert payload["name"] == "Guest"  # untouched


def test_mask_array_wildcard():
    payload = [{"psk": "a"}, {"psk": "b"}, {"psk": "c"}]
    mask_path(payload, [("array",), ("key", "psk")])
    assert payload[0]["psk"]["_redacted"] is True
    assert payload[1]["psk"]["_redacted"] is True
    assert payload[2]["psk"]["_redacted"] is True
    assert payload[0]["psk"]["_hash"] == _sha256("a")


def test_mask_missing_path_is_silent():
    """Paths that don't resolve are skipped, not raised."""
    payload = {"name": "Guest"}  # no psk
    mask_path(payload, [("key", "psk")])
    assert payload == {"name": "Guest"}


def test_mask_handles_null_value():
    """A null value at the target becomes a redacted sentinel of null."""
    payload = {"psk": None}
    mask_path(payload, [("key", "psk")])
    # null is hashed as the string "null"
    assert payload["psk"] == {"_redacted": True, "_hash": _sha256(None)}


# helper
def _sha256(value):
    import hashlib
    import json
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# Top-level redact() entry point tests ----------------------------------------

from server.config_collector.redactor import redact


def test_redact_wireless_ssids_masks_psks():
    payload = [
        {"number": 0, "name": "Corp", "enabled": True, "psk": "corppass123", "authMode": "psk"},
        {"number": 1, "name": "Guest", "enabled": True, "psk": "guestpass", "authMode": "psk"},
    ]
    redacted_str, hash_hex, byte_size, hot = redact(payload, "wireless_ssids")

    # Canonical string is valid JSON
    import json
    parsed = json.loads(redacted_str)
    assert parsed[0]["psk"] == {"_redacted": True, "_hash": _sha256("corppass123")}
    assert parsed[1]["psk"] == {"_redacted": True, "_hash": _sha256("guestpass")}
    assert parsed[0]["name"] == "Corp"  # name retained

    assert len(hash_hex) == 64
    assert byte_size == len(redacted_str.encode("utf-8"))


def test_redact_unknown_config_area_passes_through():
    """An area not in the catalog → no redaction, but still canonicalized + hashed."""
    payload = {"foo": 1}
    redacted_str, hash_hex, byte_size, hot = redact(payload, "unknown_area")
    assert redacted_str == '{"foo":1}'


def test_redact_same_payload_different_key_order_same_hash():
    a = {"b": 1, "a": 2, "c": [3, 2, 1]}
    b = {"c": [3, 2, 1], "a": 2, "b": 1}
    _, h1, _, _ = redact(a, "unknown_area")
    _, h2, _, _ = redact(b, "unknown_area")
    assert h1 == h2


def test_redact_different_secret_different_hash():
    """Hashing on the sentinel distinguishes changed secrets."""
    _, h1, _, _ = redact([{"psk": "v1"}], "wireless_ssids")
    _, h2, _, _ = redact([{"psk": "v2"}], "wireless_ssids")
    assert h1 != h2


def test_redact_extracts_name_and_enabled_hot_columns():
    payload = {"name": "Store 42", "enabled": True, "other": 123}
    _, _, _, hot = redact(payload, "unknown_area")
    assert hot == {"name_hint": "Store 42", "enabled_hint": 1}


def test_redact_hot_columns_none_when_absent():
    payload = {"other": 123}
    _, _, _, hot = redact(payload, "unknown_area")
    assert hot == {"name_hint": None, "enabled_hint": None}


# Fixture sanity tests --------------------------------------------------------

import json
from pathlib import Path


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "meraki"


def test_all_fixtures_parse_as_valid_json():
    files = list(FIXTURES_DIR.glob("*.json"))
    assert len(files) >= 3, "expected at least 3 seed fixtures"
    for f in files:
        data = json.loads(f.read_text())
        assert data is not None
