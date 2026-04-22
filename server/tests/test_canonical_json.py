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


def test_object_keys_sort_alphabetically():
    """Same object, different insertion order → same canonical output."""
    a = {"b": 1, "a": 2, "c": 3}
    b = {"c": 3, "a": 2, "b": 1}
    assert dumps(a) == dumps(b)
    assert dumps(a) == '{"a":2,"b":1,"c":3}'


def test_array_order_preserved():
    """Arrays are order-sensitive; reversing changes the output."""
    assert dumps([1, 2, 3]) == "[1,2,3]"
    assert dumps([3, 2, 1]) == "[3,2,1]"
    assert dumps([1, 2, 3]) != dumps([3, 2, 1])


def test_nested_objects_recurse():
    nested = {"outer": {"z": 1, "a": 2}, "arr": [{"y": 1, "x": 2}]}
    assert dumps(nested) == '{"arr":[{"x":2,"y":1}],"outer":{"a":2,"z":1}}'


def test_no_whitespace_or_trailing_newline():
    assert dumps({"a": 1, "b": [1, 2]}) == '{"a":1,"b":[1,2]}'
    assert not dumps({"a": 1}).endswith("\n")
