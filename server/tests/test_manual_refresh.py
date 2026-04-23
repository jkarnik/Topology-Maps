"""Tests for manual refresh (Plan 1.16)."""
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
async def test_refresh_single_area(client, conn):
    """Refresh writes an observation with source_event=manual_refresh."""
    from server.config_collector.manual_refresh import refresh_entity

    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/networks/N_1/appliance/vlans").mock(return_value=httpx.Response(200, json=[]))

        result = await refresh_entity(
            client, conn, org_id="o1",
            entity_type="network", entity_id="N_1",
            config_area="appliance_vlans",
        )

    assert result["expected_calls"] == 1
    row = conn.execute(
        "SELECT source_event FROM config_observations WHERE entity_id=? AND config_area=?",
        ("N_1", "appliance_vlans"),
    ).fetchone()
    assert row["source_event"] == "manual_refresh"


@pytest.mark.asyncio
async def test_refresh_all_areas_for_entity(client, conn):
    """When config_area is omitted, every area applicable to the entity is refreshed."""
    from server.config_collector.manual_refresh import refresh_entity

    async with respx.mock(base_url="https://api.meraki.com/api/v1", assert_all_called=False) as mock:
        mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, json=[]))

        result = await refresh_entity(
            client, conn, org_id="o1",
            entity_type="org", entity_id="o1",
            config_area=None,
        )

    from server.config_collector._endpoints_org import ORG_ENDPOINTS
    assert result["expected_calls"] == len(ORG_ENDPOINTS)
