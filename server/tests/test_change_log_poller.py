"""Tests for change-log poller (Plan 1.14)."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest
import respx
import httpx

from server.meraki_client import MerakiClient


@pytest.fixture
def client():
    return MerakiClient(api_key="test-key")


@pytest.fixture
def conn(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "topology.db"
        from server import database
        monkeypatch.setattr(database, "DB_PATH", db_path)
        c = database.get_connection()
        yield c
        c.close()


@pytest.mark.asyncio
async def test_poll_once_stores_new_events(client, conn):
    from server.config_collector.change_log_poller import poll_once

    async with respx.mock(base_url="https://api.meraki.com/api/v1", assert_all_called=False) as mock:
        mock.get("/organizations/o1/configurationChanges").mock(return_value=httpx.Response(200, json=[
            {"ts": "2026-04-22T10:00:00Z", "page": "Security & SD-WAN > Addressing & VLANs",
             "label": "VLAN", "networkId": "N_1", "oldValue": "10", "newValue": "20"},
        ]))
        mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))

        summary = await poll_once(client, conn, org_id="o1", timespan=3600)

    assert summary["new_events"] == 1
    count = conn.execute("SELECT COUNT(*) AS n FROM config_change_events").fetchone()["n"]
    assert count == 1


@pytest.mark.asyncio
async def test_poll_once_dedupes_previously_seen(client, conn):
    from server.config_collector.change_log_poller import poll_once

    event = {
        "ts": "2026-04-22T10:00:00Z", "page": "Wireless > Access Control",
        "label": "Bandwidth limit", "networkId": "N_1",
        "oldValue": "11", "newValue": "24", "ssidNumber": 3,
    }

    async with respx.mock(base_url="https://api.meraki.com/api/v1", assert_all_called=False) as mock:
        mock.get("/organizations/o1/configurationChanges").mock(return_value=httpx.Response(200, json=[event, event]))
        mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))

        summary = await poll_once(client, conn, org_id="o1", timespan=3600)

    count = conn.execute("SELECT COUNT(*) AS n FROM config_change_events").fetchone()["n"]
    assert count == 1
    assert summary["new_events"] == 1
    assert summary["duplicates"] == 1
