"""Data-access functions for the config_collector SQLite tables.

All functions take an open sqlite3.Connection as the first argument and
commit on successful writes. Reads do not commit.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_blob(
    conn: sqlite3.Connection,
    hash_hex: str,
    payload: str,
    byte_size: int,
) -> bool:
    """Insert a blob row if `hash_hex` is new. Returns True if inserted, False if existed."""
    cursor = conn.execute(
        """INSERT OR IGNORE INTO config_blobs (hash, payload, byte_size, first_seen_at)
           VALUES (?, ?, ?, ?)""",
        (hash_hex, payload, byte_size, _now_iso()),
    )
    conn.commit()
    return cursor.rowcount == 1
