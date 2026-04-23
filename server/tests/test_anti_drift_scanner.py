"""Tests for anti-drift sweep (Plan 1.15)."""
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
async def test_anti_drift_confirms_matching_hash(client, conn):
    """If the fresh payload hash matches the latest stored, source_event=anti_drift_confirm."""
    from server.config_collector.scanner import run_anti_drift_sweep
    from server.config_collector.store import insert_observation_if_changed
    from server.config_collector.redactor import redact

    admins_body = [{"id": "a1", "name": "Alice"}]
    _, hash_hex, byte_size, _ = redact(admins_body, "org_admins")
    conn.execute(
        "INSERT INTO config_blobs (hash, payload, byte_size, first_seen_at) VALUES (?,?,?,?)",
        (hash_hex, "seed_payload", byte_size, "2026-04-15T00:00:00Z"),
    )
    conn.commit()
    insert_observation_if_changed(
        conn, org_id="o1", entity_type="org", entity_id="o1",
        config_area="org_admins", sub_key=None, hash_hex=hash_hex,
        source_event="baseline", change_event_id=None, sweep_run_id=None,
        hot_columns={"name_hint": None, "enabled_hint": None},
    )

    async with respx.mock(base_url="https://api.meraki.com/api/v1", assert_all_called=False) as mock:
        mock.get("/organizations/o1/networks").mock(return_value=httpx.Response(200, json=[]))
        mock.get("/organizations/o1/devices").mock(return_value=httpx.Response(200, json=[]))
        mock.get("/organizations/o1/admins").mock(return_value=httpx.Response(200, json=admins_body))
        mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))

        await run_anti_drift_sweep(client, conn, org_id="o1")

    confirms = conn.execute(
        """SELECT * FROM config_observations
           WHERE config_area='org_admins' AND source_event='anti_drift_confirm'"""
    ).fetchall()
    assert len(confirms) >= 1


@pytest.mark.asyncio
async def test_anti_drift_discrepancy_on_hash_mismatch(client, conn):
    """If the fresh payload differs from latest stored, source_event=anti_drift_discrepancy."""
    from server.config_collector.scanner import run_anti_drift_sweep
    from server.config_collector.store import insert_observation_if_changed

    conn.execute(
        "INSERT INTO config_blobs (hash, payload, byte_size, first_seen_at) VALUES (?,?,?,?)",
        ("old_hash", "old_payload", 11, "2026-04-15T00:00:00Z"),
    )
    conn.commit()
    insert_observation_if_changed(
        conn, org_id="o1", entity_type="org", entity_id="o1",
        config_area="org_admins", sub_key=None, hash_hex="old_hash",
        source_event="baseline", change_event_id=None, sweep_run_id=None,
        hot_columns={"name_hint": None, "enabled_hint": None},
    )

    async with respx.mock(base_url="https://api.meraki.com/api/v1", assert_all_called=False) as mock:
        mock.get("/organizations/o1/networks").mock(return_value=httpx.Response(200, json=[]))
        mock.get("/organizations/o1/devices").mock(return_value=httpx.Response(200, json=[]))
        mock.get("/organizations/o1/admins").mock(return_value=httpx.Response(200, json=[{"id": "new", "name": "Changed"}]))
        mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))

        await run_anti_drift_sweep(client, conn, org_id="o1")

    discrepancies = conn.execute(
        """SELECT * FROM config_observations
           WHERE config_area='org_admins' AND source_event='anti_drift_discrepancy'"""
    ).fetchall()
    assert len(discrepancies) >= 1
