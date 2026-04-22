"""Tests for MerakiClient pagination (Plan 1.05)."""
from __future__ import annotations

import pytest
import respx
import httpx

from server.meraki_client import MerakiClient, _parse_link_header, MaxPagesExceeded


def test_parse_link_header_with_next():
    header = '<https://api.meraki.com/api/v1/foo?startingAfter=abc>; rel="next"'
    assert _parse_link_header(header) == "https://api.meraki.com/api/v1/foo?startingAfter=abc"


def test_parse_link_header_multiple_rels():
    header = (
        '<https://api.meraki.com/api/v1/foo?startingAfter=abc>; rel="next", '
        '<https://api.meraki.com/api/v1/foo>; rel="first", '
        '<https://api.meraki.com/api/v1/foo?startingAfter=xyz>; rel="last"'
    )
    assert _parse_link_header(header) == "https://api.meraki.com/api/v1/foo?startingAfter=abc"


def test_parse_link_header_no_next_returns_none():
    header = '<https://api.meraki.com/api/v1/foo>; rel="first"'
    assert _parse_link_header(header) is None


def test_parse_link_header_empty_or_none():
    assert _parse_link_header(None) is None
    assert _parse_link_header("") is None
