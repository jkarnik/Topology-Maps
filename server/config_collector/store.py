"""Data-access functions for the config_collector SQLite tables.

All functions take an open sqlite3.Connection as the first argument and
commit on successful writes. Reads do not commit.
"""
from __future__ import annotations

import json as _json
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


def get_latest_observation(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    entity_type: str,
    entity_id: str,
    config_area: str,
    sub_key: Optional[str],
) -> Optional[dict]:
    row = conn.execute(
        """SELECT * FROM config_observations
           WHERE org_id=? AND entity_type=? AND entity_id=?
             AND config_area=? AND sub_key IS ?
           ORDER BY observed_at DESC LIMIT 1""",
        (org_id, entity_type, entity_id, config_area, sub_key),
    ).fetchone()
    return dict(row) if row else None


def get_observation_history(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    entity_type: str,
    entity_id: str,
    config_area: Optional[str] = None,
    sub_key: Optional[str] = None,
    limit: int = 100,
    before_observed_at: Optional[str] = None,
) -> list[dict]:
    """Observations for an entity, newest first. Optional filter by config_area."""
    sql = """SELECT * FROM config_observations
             WHERE org_id=? AND entity_type=? AND entity_id=?"""
    params: list = [org_id, entity_type, entity_id]
    if config_area is not None:
        sql += " AND config_area=?"
        params.append(config_area)
    if sub_key is not None or config_area is not None:
        sql += " AND sub_key IS ?"
        params.append(sub_key)
    if before_observed_at is not None:
        sql += " AND observed_at < ?"
        params.append(before_observed_at)
    sql += " ORDER BY observed_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def insert_change_event(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    event: dict,
) -> Optional[int]:
    """Insert a change-log event; return its row id, or None if it was a duplicate."""
    try:
        cursor = conn.execute(
            """INSERT INTO config_change_events
               (org_id, ts, admin_id, admin_name, admin_email,
                network_id, network_name, ssid_number, ssid_name,
                page, label, old_value, new_value,
                client_id, client_description, raw_json, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                org_id,
                event.get("ts"),
                event.get("adminId"),
                event.get("adminName"),
                event.get("adminEmail"),
                event.get("networkId"),
                event.get("networkName"),
                event.get("ssidNumber"),
                event.get("ssidName"),
                event.get("page"),
                event.get("label"),
                event.get("oldValue"),
                event.get("newValue"),
                event.get("clientId"),
                event.get("clientDescription"),
                _json.dumps(event),
                _now_iso(),
            ),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None


def get_change_events(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    network_id: Optional[str] = None,
    limit: int = 100,
    before_ts: Optional[str] = None,
) -> list[dict]:
    sql = "SELECT * FROM config_change_events WHERE org_id=?"
    params: list = [org_id]
    if network_id is not None:
        sql += " AND network_id=?"
        params.append(network_id)
    if before_ts is not None:
        sql += " AND ts < ?"
        params.append(before_ts)
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)

    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def create_sweep_run(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    kind: str,
    total_calls: Optional[int] = None,
) -> int:
    cursor = conn.execute(
        """INSERT INTO config_sweep_runs (org_id, kind, status, total_calls)
           VALUES (?, ?, 'queued', ?)""",
        (org_id, kind, total_calls),
    )
    conn.commit()
    return cursor.lastrowid


def mark_sweep_running(conn: sqlite3.Connection, run_id: int) -> None:
    conn.execute(
        "UPDATE config_sweep_runs SET status='running', started_at=? WHERE id=?",
        (_now_iso(), run_id),
    )
    conn.commit()


def increment_sweep_counters(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    completed: int = 0,
    failed: int = 0,
    skipped: int = 0,
) -> None:
    conn.execute(
        """UPDATE config_sweep_runs SET
             completed_calls = completed_calls + ?,
             failed_calls = failed_calls + ?,
             skipped_calls = skipped_calls + ?
           WHERE id=?""",
        (completed, failed, skipped, run_id),
    )
    conn.commit()


def mark_sweep_complete(conn: sqlite3.Connection, run_id: int) -> None:
    conn.execute(
        "UPDATE config_sweep_runs SET status='complete', completed_at=? WHERE id=?",
        (_now_iso(), run_id),
    )
    conn.commit()


def mark_sweep_failed(conn: sqlite3.Connection, run_id: int, *, error_summary: str) -> None:
    conn.execute(
        "UPDATE config_sweep_runs SET status='failed', completed_at=?, error_summary=? WHERE id=?",
        (_now_iso(), error_summary, run_id),
    )
    conn.commit()


def list_completed_entity_areas(
    conn: sqlite3.Connection,
    *,
    sweep_run_id: int,
) -> set[tuple[str, str, str, Optional[str]]]:
    """Return set of (entity_type, entity_id, config_area, sub_key) tuples with
    at least one observation under this sweep_run_id. Used for resumability."""
    rows = conn.execute(
        """SELECT DISTINCT entity_type, entity_id, config_area, sub_key
           FROM config_observations WHERE sweep_run_id=?""",
        (sweep_run_id,),
    ).fetchall()
    return {(r["entity_type"], r["entity_id"], r["config_area"], r["sub_key"]) for r in rows}


def get_active_sweep_run(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    kind: str,
) -> Optional[dict]:
    """Return the most recent queued/running sweep of `kind` for `org_id`, or None."""
    row = conn.execute(
        """SELECT * FROM config_sweep_runs
           WHERE org_id=? AND kind=? AND status IN ('queued', 'running')
           ORDER BY id DESC LIMIT 1""",
        (org_id, kind),
    ).fetchone()
    return dict(row) if row else None


def update_sweep_total_calls(
    conn: sqlite3.Connection,
    run_id: int,
    total_calls: int,
) -> None:
    """Set total_calls on an existing sweep_runs row (used after enumeration)."""
    conn.execute(
        "UPDATE config_sweep_runs SET total_calls=? WHERE id=?",
        (total_calls, run_id),
    )
    conn.commit()


def get_observations_in_window(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    from_ts: str,
    to_ts: str,
) -> list[dict]:
    """Return one row per (entity_type, entity_id, config_area, sub_key) that has
    at least one observation in the org. Each row carries the latest hash at or
    before from_ts ('from_hash') and the latest hash at or before to_ts ('to_hash').
    Rows where both hashes are identical (no change) are excluded.
    Uses window functions to avoid N+1 blob fetches."""
    sql = """
    WITH ranked AS (
        SELECT
            entity_type, entity_id, config_area, sub_key, hash, observed_at,
            change_event_id, name_hint,
            ROW_NUMBER() OVER (
                PARTITION BY entity_type, entity_id, config_area, sub_key
                ORDER BY CASE WHEN observed_at <= :from_ts THEN 1 ELSE 2 END,
                         observed_at DESC
            ) AS rn_from,
            ROW_NUMBER() OVER (
                PARTITION BY entity_type, entity_id, config_area, sub_key
                ORDER BY CASE WHEN observed_at <= :to_ts THEN 1 ELSE 2 END,
                         observed_at DESC
            ) AS rn_to
        FROM config_observations
        WHERE org_id = :org_id
    ),
    from_snap AS (
        SELECT entity_type, entity_id, config_area, sub_key, hash AS from_hash, name_hint
        FROM ranked
        WHERE rn_from = 1 AND observed_at <= :from_ts
    ),
    to_snap AS (
        SELECT entity_type, entity_id, config_area, sub_key, hash AS to_hash,
               observed_at AS to_observed_at, change_event_id, name_hint
        FROM ranked
        WHERE rn_to = 1 AND observed_at <= :to_ts
    )
    SELECT
        COALESCE(t.entity_type, f.entity_type) AS entity_type,
        COALESCE(t.entity_id,   f.entity_id)   AS entity_id,
        COALESCE(t.config_area, f.config_area) AS config_area,
        COALESCE(t.sub_key,     f.sub_key)     AS sub_key,
        f.from_hash,
        t.to_hash,
        COALESCE(ce.ts, t.to_observed_at)      AS to_observed_at,
        COALESCE(t.name_hint, f.name_hint, '') AS name_hint
    FROM to_snap t
    LEFT JOIN from_snap f ON (
        t.entity_type = f.entity_type
        AND t.entity_id   = f.entity_id
        AND t.config_area = f.config_area
        AND t.sub_key IS f.sub_key
    )
    LEFT JOIN config_change_events ce ON ce.id = t.change_event_id
    WHERE (f.from_hash IS NULL OR f.from_hash != t.to_hash)
    ORDER BY t.entity_type, t.entity_id, t.config_area, t.sub_key
    """
    cursor = conn.execute(sql, {"org_id": org_id, "from_ts": from_ts, "to_ts": to_ts})
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]
