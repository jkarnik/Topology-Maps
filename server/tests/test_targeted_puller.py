"""Tests for targeted_puller (Plan 1.12)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import respx
import httpx

from server.meraki_client import MerakiClient


@pytest.fixture
def conn(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "topology.db"
        from server import database
        monkeypatch.setattr(database, "DB_PATH", db_path)
        c = database.get_connection()
        yield c
        c.close()


@pytest.fixture
def client():
    return MerakiClient(api_key="test-key")


def test_coalesce_removes_duplicates():
    from server.config_collector.targeted_puller import coalesce_jobs

    jobs = [
        {"url": "/a", "config_area": "vlans", "entity_type": "network", "entity_id": "N1", "sub_key": None, "paginated": False, "scope": "network"},
        {"url": "/a", "config_area": "vlans", "entity_type": "network", "entity_id": "N1", "sub_key": None, "paginated": False, "scope": "network"},
        {"url": "/b", "config_area": "ports", "entity_type": "device", "entity_id": "Q-A", "sub_key": None, "paginated": False, "scope": "device"},
    ]
    result = list(coalesce_jobs(jobs))
    assert len(result) == 2
    assert {r["url"] for r in result} == {"/a", "/b"}


def test_coalesce_treats_different_sub_keys_as_distinct():
    from server.config_collector.targeted_puller import coalesce_jobs

    jobs = [
        {"url": "/ssids/0/fw", "config_area": "wireless_ssid_l3_firewall", "entity_type": "ssid", "entity_id": "N:0", "sub_key": "0", "paginated": False, "scope": "ssid"},
        {"url": "/ssids/1/fw", "config_area": "wireless_ssid_l3_firewall", "entity_type": "ssid", "entity_id": "N:1", "sub_key": "1", "paginated": False, "scope": "ssid"},
    ]
    assert len(list(coalesce_jobs(jobs))) == 2


@pytest.mark.asyncio
async def test_pull_many_single_job_writes_observation(client, conn):
    from server.config_collector.targeted_puller import pull_many

    jobs = [{
        "url": "/networks/N_1/appliance/vlans",
        "config_area": "appliance_vlans",
        "entity_type": "network",
        "entity_id": "N_1",
        "sub_key": None,
        "paginated": False,
        "scope": "network",
    }]

    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/networks/N_1/appliance/vlans").mock(
            return_value=httpx.Response(200, json=[{"id": 10, "name": "Data"}])
        )
        summary = await pull_many(
            client=client, conn=conn, jobs=jobs,
            org_id="o1", sweep_run_id=None, source_event="manual_refresh",
        )
    assert summary.successes == 1
    assert summary.failures == 0

    row = conn.execute(
        "SELECT * FROM config_observations WHERE entity_id=? AND config_area=?",
        ("N_1", "appliance_vlans"),
    ).fetchone()
    assert row is not None
    assert row["source_event"] == "manual_refresh"


@pytest.mark.asyncio
async def test_pull_many_skips_unchanged_hash(client, conn):
    """Same payload twice → second call is skipped (no new row)."""
    from server.config_collector.targeted_puller import pull_many

    job = {
        "url": "/networks/N_1/appliance/vlans",
        "config_area": "appliance_vlans",
        "entity_type": "network", "entity_id": "N_1",
        "sub_key": None, "paginated": False, "scope": "network",
    }

    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/networks/N_1/appliance/vlans").mock(
            return_value=httpx.Response(200, json=[{"id": 10}])
        )
        await pull_many(client=client, conn=conn, jobs=[job], org_id="o1", sweep_run_id=None, source_event="change_log")
        summary = await pull_many(client=client, conn=conn, jobs=[job], org_id="o1", sweep_run_id=None, source_event="change_log")

    assert summary.successes == 0
    assert summary.skipped_unchanged == 1

    count = conn.execute("SELECT COUNT(*) AS n FROM config_observations").fetchone()["n"]
    assert count == 1


@pytest.mark.asyncio
async def test_pull_many_records_http_failure(client, conn):
    from server.config_collector.targeted_puller import pull_many

    job = {
        "url": "/networks/N_1/appliance/vlans",
        "config_area": "appliance_vlans",
        "entity_type": "network", "entity_id": "N_1",
        "sub_key": None, "paginated": False, "scope": "network",
    }

    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/networks/N_1/appliance/vlans").mock(return_value=httpx.Response(500, json={"error": "oops"}))
        summary = await pull_many(client=client, conn=conn, jobs=[job], org_id="o1", sweep_run_id=None, source_event="baseline")

    assert summary.failures == 1
    assert summary.successes == 0
    assert len(summary.errors) == 1
    assert "/networks/N_1/appliance/vlans" in summary.errors[0][0]
