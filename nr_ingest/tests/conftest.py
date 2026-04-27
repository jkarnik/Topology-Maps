# nr_ingest/tests/conftest.py
from __future__ import annotations
import sqlite3
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "server"))
sys.path.insert(0, str(Path(__file__).parent.parent))

CONFIG_SCHEMA = """
    CREATE TABLE IF NOT EXISTS config_blobs (
        hash TEXT PRIMARY KEY, payload TEXT NOT NULL,
        byte_size INTEGER NOT NULL, first_seen_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS config_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
        config_area TEXT NOT NULL, sub_key TEXT, hash TEXT NOT NULL,
        observed_at TEXT NOT NULL, source_event TEXT NOT NULL,
        change_event_id INTEGER, sweep_run_id INTEGER,
        name_hint TEXT, enabled_hint INTEGER
    );
"""

@pytest.fixture
def test_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(CONFIG_SCHEMA)
    yield conn
    conn.close()
