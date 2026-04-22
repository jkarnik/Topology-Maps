"""Tests for canonical JSON serialization (Plan 1.02)."""
from __future__ import annotations

import pytest

from server.config_collector.canonical_json import dumps


def test_flat_types_serialize_deterministically():
    assert dumps(None) == "null"
    assert dumps(True) == "true"
    assert dumps(False) == "false"
    assert dumps(0) == "0"
    assert dumps(42) == "42"
    assert dumps(-17) == "-17"
    assert dumps("hello") == '"hello"'
    assert dumps("") == '""'


def test_unicode_preserved_not_escaped():
    """Non-ASCII characters are kept as UTF-8, not \\u-escaped."""
    assert dumps("café") == '"café"'
    assert dumps("日本語") == '"日本語"'
