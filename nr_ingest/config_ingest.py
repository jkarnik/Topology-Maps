# nr_ingest/config_ingest.py
"""Push Meraki config data from topology.db to New Relic as custom events.

Usage:
    python3 nr_ingest/config_ingest.py              # push all data
    python3 nr_ingest/config_ingest.py --since 2h   # only changes in last 2 hours
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx

_DIR = Path(__file__).parent
_PROJECT_ROOT = _DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT / "server"))

from config_collector.diff_engine import compute_diff  # noqa: E402

_ENV_FILE = _PROJECT_ROOT / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

NR_EVENT_API = "https://insights-collector.newrelic.com/v1/accounts/{account_id}/events"
MARKER_FILE = _DIR / "data" / ".last_config_ingest"


def build_snapshot_events(conn: sqlite3.Connection) -> list[dict]:
    """Return one MerakiConfigSnapshot event per (entity, config_area), latest only."""
    sql = """
        SELECT
            o.org_id, o.entity_type, o.entity_id, o.config_area, o.sub_key,
            o.hash AS config_hash, o.observed_at, o.sweep_run_id,
            COALESCE(o.name_hint, '') AS entity_name,
            b.payload AS config_json
        FROM config_observations o
        JOIN config_blobs b ON b.hash = o.hash
        WHERE o.id = (
            SELECT id FROM config_observations i
            WHERE i.org_id = o.org_id AND i.entity_type = o.entity_type
              AND i.entity_id = o.entity_id AND i.config_area = o.config_area
              AND i.sub_key IS o.sub_key
            ORDER BY i.observed_at DESC, i.id DESC LIMIT 1
        )
        ORDER BY o.entity_type, o.entity_id, o.config_area
    """
    return [
        {
            "eventType": "MerakiConfigSnapshot",
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "entity_name": row["entity_name"],
            "config_area": row["config_area"],
            "sub_key": row["sub_key"] or "",
            "config_hash": row["config_hash"],
            "config_json": row["config_json"],
            "org_id": row["org_id"],
            "network_id": "",
            "sweep_run_id": row["sweep_run_id"] or 0,
            "tags.source": "topology-maps-app",
        }
        for row in conn.execute(sql).fetchall()
    ]


def _compute_change_summary(diff_result) -> str:
    """Summarise a DiffResult as 'N added, M removed, K changed'."""
    from config_collector.diff_engine import RowAdded, RowRemoved, RowChanged, FieldChanged, FieldAdded, FieldRemoved, SecretChanged
    added = sum(1 for c in diff_result.changes if isinstance(c, (RowAdded, FieldAdded)))
    removed = sum(1 for c in diff_result.changes if isinstance(c, (RowRemoved, FieldRemoved)))
    changed = sum(1 for c in diff_result.changes if isinstance(c, (RowChanged, FieldChanged)))
    secret = sum(1 for c in diff_result.changes if isinstance(c, SecretChanged))
    parts = []
    if added:
        parts.append(f"{added} added")
    if removed:
        parts.append(f"{removed} removed")
    if changed:
        parts.append(f"{changed} changed")
    if secret:
        parts.append(f"{secret} secret rotated")
    return ", ".join(parts) if parts else "no changes"


def _serialize_diff(diff_result) -> str:
    """Serialize DiffResult.changes to JSON."""
    import dataclasses
    return json.dumps([dataclasses.asdict(c) for c in diff_result.changes])


def build_change_events(conn: sqlite3.Connection, since_ts: Optional[str]) -> list[dict]:
    """Return MerakiConfigChange events for hash changes detected after since_ts."""
    sql = """
        SELECT
            a.org_id, a.entity_type, a.entity_id, a.config_area, a.sub_key,
            COALESCE(a.name_hint, '') AS entity_name,
            a.hash AS to_hash, a.observed_at AS detected_at,
            prev.hash AS from_hash,
            b_new.payload AS to_payload, b_old.payload AS from_payload
        FROM config_observations a
        LEFT JOIN config_observations prev ON (
            prev.org_id = a.org_id AND prev.entity_type = a.entity_type
            AND prev.entity_id = a.entity_id AND prev.config_area = a.config_area
            AND prev.sub_key IS a.sub_key
            AND prev.id = (
                SELECT id FROM config_observations x
                WHERE x.org_id = a.org_id AND x.entity_type = a.entity_type
                  AND x.entity_id = a.entity_id AND x.config_area = a.config_area
                  AND x.sub_key IS a.sub_key AND x.observed_at < a.observed_at
                ORDER BY x.observed_at DESC, x.id DESC LIMIT 1
            )
        )
        JOIN config_blobs b_new ON b_new.hash = a.hash
        LEFT JOIN config_blobs b_old ON b_old.hash = prev.hash
        WHERE prev.hash IS NOT NULL
          AND prev.hash != a.hash
          AND (? IS NULL OR a.observed_at > ?)
        ORDER BY a.observed_at
    """
    rows = conn.execute(sql, (since_ts, since_ts)).fetchall()
    events = []
    for row in rows:
        try:
            diff = compute_diff(json.loads(row["from_payload"]), json.loads(row["to_payload"]))
            diff_json = _serialize_diff(diff)
            summary = _compute_change_summary(diff)
        except Exception as exc:
            print(f"[warn] diff failed for {row['entity_id']}/{row['config_area']}: {exc}", file=sys.stderr)
            diff_json = "[]"
            summary = "diff unavailable"
        events.append({
            "eventType": "MerakiConfigChange",
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "entity_name": row["entity_name"],
            "config_area": row["config_area"],
            "sub_key": row["sub_key"] or "",
            "from_hash": row["from_hash"],
            "to_hash": row["to_hash"],
            "diff_json": diff_json,
            "change_summary": summary,
            "detected_at": row["detected_at"],
            "org_id": row["org_id"],
            "network_id": "",
            "tags.source": "topology-maps-app",
        })
    return events


def read_marker(marker_path: Path = MARKER_FILE) -> Optional[str]:
    """Return last successful ingest timestamp, or None if no marker exists."""
    if marker_path.exists():
        return marker_path.read_text().strip() or None
    return None


def write_marker(ts: str, marker_path: Path = MARKER_FILE) -> None:
    """Record a successful ingest timestamp."""
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(ts)


def parse_since(since_str: Optional[str]) -> Optional[str]:
    """Convert a duration string like '2h' or '30m' to an ISO UTC timestamp."""
    if since_str is None:
        return None
    m = re.fullmatch(r"(\d+)([hm])", since_str.strip(), re.IGNORECASE)
    if not m:
        raise ValueError(f"Invalid --since format: {since_str!r}. Use e.g. '2h' or '30m'.")
    value, unit = int(m.group(1)), m.group(2).lower()
    if value == 0:
        raise ValueError(f"--since value must be > 0, got: {since_str!r}")
    delta = timedelta(hours=value) if unit == "h" else timedelta(minutes=value)
    cutoff = datetime.now(timezone.utc) - delta
    return cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
