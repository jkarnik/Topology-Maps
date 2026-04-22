"""Tests for the redactor walker (Plan 1.03)."""
from __future__ import annotations

import pytest

from server.config_collector.redactor import parse_path


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
