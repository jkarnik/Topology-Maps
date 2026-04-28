# nr_ingest/config_ingest.py
"""Push Meraki config data from topology.db to New Relic as custom events.

Usage:
    python3 nr_ingest/config_ingest.py              # push all data
    python3 nr_ingest/config_ingest.py --since 2h   # only changes in last 2 hours
"""
from __future__ import annotations

import argparse
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
from config_data_source import load_config_db  # noqa: E402

_ENV_FILE = _PROJECT_ROOT / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

NR_EVENT_API = "https://insights-collector.newrelic.com/v1/accounts/{account_id}/events"
MARKER_FILE = _DIR / "data" / ".last_config_ingest"


def _build_entity_meta(conn: sqlite3.Connection) -> dict[str, dict]:
    """Return {entity_id: {network_id, name}} from metadata blobs for devices and networks."""
    sql = """
        SELECT o.entity_type, o.entity_id, b.payload
        FROM config_observations o
        JOIN config_blobs b ON b.hash = o.hash
        WHERE o.config_area IN ('device_metadata', 'network_metadata')
          AND o.id = (
            SELECT id FROM config_observations i
            WHERE i.entity_type = o.entity_type AND i.config_area = o.config_area
              AND i.entity_id = o.entity_id
            ORDER BY i.observed_at DESC, i.id DESC LIMIT 1
          )
    """
    result: dict[str, dict] = {}
    for row in conn.execute(sql).fetchall():
        try:
            payload = json.loads(row["payload"])
            entry = result.setdefault(row["entity_id"], {})
            if payload.get("name"):
                entry["name"] = payload["name"]
            if row["entity_type"] == "device" and payload.get("networkId"):
                entry["network_id"] = payload["networkId"]
        except Exception:
            pass
    return result


def _derive_network_id(entity_type: str, entity_id: str, entity_meta: dict) -> str:
    if entity_type == "network":
        return entity_id
    if entity_type == "ssid":
        return entity_id.split(":")[0]
    if entity_type == "device":
        return entity_meta.get(entity_id, {}).get("network_id", "")
    return ""


def _derive_name(entity_id: str, name_hint: Optional[str], entity_meta: dict) -> str:
    if name_hint:
        return name_hint
    return entity_meta.get(entity_id, {}).get("name", "")


def build_snapshot_events(conn: sqlite3.Connection) -> list[dict]:
    """Return one MerakiConfigSnapshot event per (entity, config_area), latest only."""
    entity_meta = _build_entity_meta(conn)
    sql = """
        SELECT
            o.org_id, o.entity_type, o.entity_id, o.config_area, o.sub_key,
            o.hash AS config_hash, o.observed_at, o.sweep_run_id,
            o.name_hint,
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
            "entity_name": _derive_name(row["entity_id"], row["name_hint"], entity_meta),
            "config_area": row["config_area"],
            "sub_key": row["sub_key"] or "",
            "config_hash": row["config_hash"],
            "config_json": row["config_json"][:4000],
            "org_id": row["org_id"],
            "network_id": _derive_network_id(row["entity_type"], row["entity_id"], entity_meta),
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


def build_change_events(conn: sqlite3.Connection, since_ts: Optional[str], entity_meta: Optional[dict] = None) -> list[dict]:
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
    if entity_meta is None:
        entity_meta = _build_entity_meta(conn)
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
            "diff_json": diff_json[:4000],
            "change_summary": summary,
            "detected_at": row["detected_at"],
            "org_id": row["org_id"],
            "network_id": _derive_network_id(row["entity_type"], row["entity_id"], entity_meta),
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


def chunked(lst: list, size: int):
    """Yield successive size-length chunks from lst."""
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def post_events_batch(url: str, headers: dict, events: list[dict]) -> bool:
    """POST events to NR Events API. Returns True on success, False on failure."""
    resp = httpx.post(url, headers=headers, json=events, timeout=30.0)
    if resp.status_code != 200:
        print(f"  FAILED {resp.status_code}: {resp.text}", file=sys.stderr)
        return False
    return True


def main(
    since_override: Optional[str] = None,
    marker_path: Path = MARKER_FILE,
) -> int:
    """Main entry point. Returns exit code (0 = success, 1 = failure)."""
    license_key = os.environ.get("NR_LICENSE_KEY")
    account_id = os.environ.get("NR_ACCOUNT_ID")
    if not license_key or not account_id:
        missing = [k for k in ("NR_LICENSE_KEY", "NR_ACCOUNT_ID") if not os.environ.get(k)]
        print(f"ERROR: missing required env vars: {', '.join(missing)}. Set them in .env or the environment.", file=sys.stderr)
        return 1
    url = NR_EVENT_API.format(account_id=account_id)
    headers = {"Api-Key": license_key, "Content-Type": "application/json"}

    conn = load_config_db()

    since_ts = since_override if since_override is not None else read_marker(marker_path=marker_path)

    entity_meta = _build_entity_meta(conn)
    snapshot_events = build_snapshot_events(conn)
    change_events = build_change_events(conn, since_ts=since_ts, entity_meta=entity_meta)
    all_events = snapshot_events + change_events

    print(f"Snapshot events:  {len(snapshot_events)}")
    print(f"Change events:    {len(change_events)}")
    print(f"Total to push:    {len(all_events)}")

    if not all_events:
        print("Nothing to push.")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        write_marker(now, marker_path=marker_path)
        return 0

    total_sent = 0
    for batch_num, batch in enumerate(chunked(all_events, 50), start=1):
        print(f"Batch {batch_num}: posting {len(batch)} events...")
        if not post_events_batch(url, headers, batch):
            print("Aborting — batch failed.", file=sys.stderr)
            return 1
        total_sent += len(batch)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_marker(now, marker_path=marker_path)
    print(f"\nAll {total_sent} events accepted. Marker updated: {now}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Push Meraki config events to New Relic")
    parser.add_argument("--since", metavar="DURATION",
                        help="Override since-timestamp, e.g. '2h' or '30m'")
    args = parser.parse_args()

    since = parse_since(args.since) if args.since else None
    sys.exit(main(since_override=since))
