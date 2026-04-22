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


import os


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MERAKI_API_KEY", "test-key")
    c = MerakiClient(api_key="test-key")
    yield c


@pytest.mark.asyncio
async def test_get_paginated_single_page_no_link(client):
    """A response without a Link header returns just the body."""
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/123/admins").mock(
            return_value=httpx.Response(200, json=[{"id": "1"}, {"id": "2"}])
        )
        result = await client._get_paginated("/organizations/123/admins")
    assert result == [{"id": "1"}, {"id": "2"}]
