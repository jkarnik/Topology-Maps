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


def get_blob_by_hash(conn: sqlite3.Connection, hash_hex: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT hash, payload, byte_size, first_seen_at FROM config_blobs WHERE hash=?",
        (hash_hex,),
    ).fetchone()
    return dict(row) if row else None


_ALWAYS_WRITE_SOURCE_EVENTS = {"anti_drift_confirm", "anti_drift_discrepancy", "manual_refresh"}


def insert_observation_if_changed(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    entity_type: str,
    entity_id: str,
    config_area: str,
    sub_key: Optional[str],
    hash_hex: str,
    source_event: str,
    change_event_id: Optional[int],
    sweep_run_id: Optional[int],
    hot_columns: dict,
) -> bool:
    """Insert an observation row unless the latest observation has the same hash."""
    if source_event not in _ALWAYS_WRITE_SOURCE_EVENTS:
        latest = conn.execute(
            """SELECT hash FROM config_observations
               WHERE org_id=? AND entity_type=? AND entity_id=?
                 AND config_area=? AND sub_key IS ?
               ORDER BY observed_at DESC LIMIT 1""",
            (org_id, entity_type, entity_id, config_area, sub_key),
        ).fetchone()
        if latest is not None and latest["hash"] == hash_hex:
            return False

    conn.execute(
        """INSERT INTO config_observations
           (org_id, entity_type, entity_id, config_area, sub_key,
            hash, observed_at, source_event, change_event_id, sweep_run_id,
            name_hint, enabled_hint)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            org_id, entity_type, entity_id, config_area, sub_key,
            hash_hex, _now_iso(), source_event, change_event_id, sweep_run_id,
            hot_columns.get("name_hint"), hot_columns.get("enabled_hint"),
        ),
    )
    conn.commit()
    return True
