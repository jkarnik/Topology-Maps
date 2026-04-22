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
