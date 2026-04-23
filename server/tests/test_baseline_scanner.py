"""Tests for baseline scanner (Plan 1.13)."""
from __future__ import annotations

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
async def test_enumerate_org_composition(client):
    from server.config_collector.scanner import enumerate_org_composition

    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/o1/networks").mock(return_value=httpx.Response(200, json=[
            {"id": "N_1", "name": "Store 1", "productTypes": ["appliance", "switch", "wireless"]},
            {"id": "N_2", "name": "Store 2", "productTypes": ["wireless"]},
        ]))
        mock.get("/organizations/o1/devices").mock(return_value=httpx.Response(200, json=[
            {"serial": "Q2SW-1", "networkId": "N_1", "productType": "switch"},
            {"serial": "Q2MR-1", "networkId": "N_1", "productType": "wireless"},
            {"serial": "Q2MR-2", "networkId": "N_2", "productType": "wireless"},
        ]))
        mock.get("/networks/N_1/wireless/ssids").mock(return_value=httpx.Response(200, json=[
            {"number": 0, "enabled": True},
            {"number": 1, "enabled": False},
            {"number": 2, "enabled": True},
        ]))
        mock.get("/networks/N_2/wireless/ssids").mock(return_value=httpx.Response(200, json=[
            {"number": 0, "enabled": True},
        ]))

        composition = await enumerate_org_composition(client, org_id="o1")

    assert len(composition["networks"]) == 2
    assert composition["devices_by_network"]["N_1"] == [
        {"serial": "Q2SW-1", "networkId": "N_1", "productType": "switch"},
        {"serial": "Q2MR-1", "networkId": "N_1", "productType": "wireless"},
    ]
    assert composition["enabled_ssids_by_network"]["N_1"] == [0, 2]
    assert composition["enabled_ssids_by_network"]["N_2"] == [0]


@pytest.mark.asyncio
async def test_run_baseline_writes_observations_and_marks_complete(client, conn):
    """Minimal happy-path baseline: one wireless-only network, one AP."""
    from server.config_collector.scanner import run_baseline

    async with respx.mock(base_url="https://api.meraki.com/api/v1", assert_all_called=False) as mock:
        mock.get("/organizations/o1/networks").mock(return_value=httpx.Response(200, json=[
            {"id": "N_W", "productTypes": ["wireless"]},
        ]))
        mock.get("/organizations/o1/devices").mock(return_value=httpx.Response(200, json=[
            {"serial": "Q2MR-1", "networkId": "N_W", "productType": "wireless"},
        ]))
        mock.get("/networks/N_W/wireless/ssids").mock(return_value=httpx.Response(200, json=[
            {"number": 0, "enabled": True},
        ]))
        mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))

        run_id = await run_baseline(client, conn, org_id="o1")

    row = conn.execute("SELECT status FROM config_sweep_runs WHERE id=?", (run_id,)).fetchone()
    assert row["status"] == "complete"

    count = conn.execute("SELECT COUNT(*) AS n FROM config_observations").fetchone()["n"]
    assert count > 0
