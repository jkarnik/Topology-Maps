"""Tests for config-collection schema migration (Plan 1.01)."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def fresh_db(monkeypatch):
    """Fresh SQLite DB for a single test; auto-cleaned."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "topology.db"
        # Patch DB_PATH so get_connection() uses the temp DB
        from server import database
        monkeypatch.setattr(database, "DB_PATH", db_path)
        conn = database.get_connection()
        yield conn
        conn.close()


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def test_scaffolding_loads():
    """Sanity check: test file imports and helpers resolve."""
    assert _table_exists is not None
    assert _index_exists is not None
