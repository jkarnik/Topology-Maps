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
