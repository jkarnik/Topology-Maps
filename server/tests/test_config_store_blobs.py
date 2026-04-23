"""Tests for config_blobs data access (Plan 1.10)."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def conn(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "topology.db"
        from server import database
        monkeypatch.setattr(database, "DB_PATH", db_path)
        c = database.get_connection()
        yield c
        c.close()


def test_upsert_blob_inserts_new(conn):
    from server.config_collector.store import upsert_blob

    inserted = upsert_blob(conn, hash_hex="abc123", payload='{"a":1}', byte_size=7)
    assert inserted is True

    row = conn.execute("SELECT payload, byte_size FROM config_blobs WHERE hash=?", ("abc123",)).fetchone()
    assert row["payload"] == '{"a":1}'
    assert row["byte_size"] == 7


def test_upsert_blob_dedupes_on_hash(conn):
    from server.config_collector.store import upsert_blob

    upsert_blob(conn, hash_hex="abc123", payload='{"a":1}', byte_size=7)
    inserted = upsert_blob(conn, hash_hex="abc123", payload='{"a":1}', byte_size=7)
    assert inserted is False

    count = conn.execute("SELECT COUNT(*) AS n FROM config_blobs WHERE hash=?", ("abc123",)).fetchone()["n"]
    assert count == 1


def test_upsert_blob_different_hashes_are_separate(conn):
    from server.config_collector.store import upsert_blob

    upsert_blob(conn, hash_hex="abc", payload="{}", byte_size=2)
    upsert_blob(conn, hash_hex="def", payload="[]", byte_size=2)

    count = conn.execute("SELECT COUNT(*) AS n FROM config_blobs").fetchone()["n"]
    assert count == 2


def test_get_blob_by_hash_returns_payload(conn):
    from server.config_collector.store import upsert_blob, get_blob_by_hash

    upsert_blob(conn, hash_hex="abc123", payload='{"a":1}', byte_size=7)
    blob = get_blob_by_hash(conn, "abc123")
    assert blob is not None
    assert blob["payload"] == '{"a":1}'
    assert blob["byte_size"] == 7
    assert "first_seen_at" in blob


def test_get_blob_by_hash_missing_returns_none(conn):
    from server.config_collector.store import get_blob_by_hash

    assert get_blob_by_hash(conn, "does-not-exist") is None
