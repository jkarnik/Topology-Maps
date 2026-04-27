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
            ORDER BY i.observed_at DESC LIMIT 1
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
