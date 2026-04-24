"""SQLite persistence layer.

Stores the Meraki topology cache (plus future config tables) in a single
file at `data/app.db`.  Using stdlib `sqlite3` — no extra deps — with sync
I/O executed inside FastAPI's threadpool via `def` endpoints.

Schema is created on startup with `CREATE TABLE IF NOT EXISTS`, so
deploying a new binary against an older DB works as long as columns only
get added.  If we need destructive migrations later we'll add a simple
`schema_version` row in `meta`.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any, Optional

logger = logging.getLogger(__name__)

DB_PATH = Path("data/app.db")

# `sqlite3.Connection` is not thread-safe for parallel use — we serialize
# writes through this lock.  Reads are fine concurrently in WAL mode.
_write_lock = Lock()
_connection: Optional[sqlite3.Connection] = None


# --------------------------------------------------------------------------- #
# Connection + schema bootstrap
# --------------------------------------------------------------------------- #


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        DB_PATH,
        check_same_thread=False,  # We guard writes with _write_lock.
        isolation_level=None,      # Autocommit; explicit BEGIN/COMMIT per op.
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Open the connection and ensure all tables exist."""
    global _connection
    with _write_lock:
        if _connection is not None:
            return
        _connection = _connect()
        _connection.executescript(
            """
            -- Scalar metadata (orgName, selectedNetwork, lastUpdated, schema_version, …).
            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            -- Org registry: one row per Meraki organisation.
            CREATE TABLE IF NOT EXISTS orgs (
                id   TEXT PRIMARY KEY,
                name TEXT NOT NULL
            );

            -- Flat Meraki networks list used to populate the dropdown.
            CREATE TABLE IF NOT EXISTS networks (
                id            TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                product_types TEXT NOT NULL,  -- JSON array
                org_id        TEXT REFERENCES orgs(id)
            );

            -- Per-network topology cache.  Key is a Meraki network ID or the
            -- '__all__' sentinel for the aggregated All-Networks payload.
            CREATE TABLE IF NOT EXISTS topology_cache (
                cache_key  TEXT PRIMARY KEY,
                payload    TEXT NOT NULL,           -- {l2, l3, deviceDetails} as JSON
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        _migrate(_connection)
    logger.info("SQLite DB initialised at %s", DB_PATH)


def close_db() -> None:
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply incremental schema migrations based on schema_version in meta."""
    version_str = conn.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()
    version = int(version_str[0]) if version_str and version_str[0] else 0

    if version < 3:
        conn.execute("BEGIN")
        cols = {r[1] for r in conn.execute("PRAGMA table_info(networks)").fetchall()}
        if "org_id" not in cols:
            conn.execute("ALTER TABLE networks ADD COLUMN org_id TEXT REFERENCES orgs(id)")
        conn.execute(
            "INSERT INTO meta(key, value) VALUES ('schema_version', '3') "
            "ON CONFLICT(key) DO UPDATE SET value = '3'"
        )
        conn.execute("COMMIT")


def _conn() -> sqlite3.Connection:
    if _connection is None:
        init_db()
    assert _connection is not None
    return _connection


# --------------------------------------------------------------------------- #
# Meta helpers — scalar key/value
# --------------------------------------------------------------------------- #


def meta_get(key: str) -> Optional[str]:
    row = _conn().execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def meta_set(key: str, value: Optional[str]) -> None:
    with _write_lock:
        _conn().execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


# --------------------------------------------------------------------------- #
# Topology cache + networks — whole-snapshot replace
# --------------------------------------------------------------------------- #


def save_snapshot(snapshot: dict[str, Any]) -> int:
    """Replace the entire topology cache with the given snapshot.

    Shape mirrors the old `meraki-topology-seed.json` schema v2:
        {
            "version": 2,
            "orgName": str | None,
            "networks": [{id, name, productTypes}, ...],
            "selectedNetwork": str | None,
            "topology": { cache_key: {l2, l3, deviceDetails} },
            "lastUpdated": str | None   # ISO 8601
        }

    Returns the number of topology cache rows written.
    """
    version = snapshot.get("version")
    org_name = snapshot.get("orgName")
    networks: list[dict[str, Any]] = snapshot.get("networks") or []
    selected_network = snapshot.get("selectedNetwork")
    topology: dict[str, dict] = snapshot.get("topology") or {}
    last_updated = snapshot.get("lastUpdated")

    with _write_lock:
        conn = _conn()
        try:
            conn.execute("BEGIN")

            # Scalar meta
            for key, value in {
                "schema_version": "3",
                "orgName": org_name,
                "selectedNetwork": selected_network,
                "lastUpdated": last_updated,
            }.items():
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )

            # Networks — full replace
            conn.execute("DELETE FROM networks")
            conn.executemany(
                "INSERT INTO networks(id, name, product_types) VALUES (?, ?, ?)",
                [
                    (
                        n.get("id"),
                        n.get("name"),
                        json.dumps(n.get("productTypes") or []),
                    )
                    for n in networks
                    if n.get("id")
                ],
            )

            # Topology cache — full replace
            conn.execute("DELETE FROM topology_cache")
            conn.executemany(
                "INSERT INTO topology_cache(cache_key, payload) VALUES (?, ?)",
                [(key, json.dumps(payload)) for key, payload in topology.items()],
            )

            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    return len(topology)


def load_snapshot() -> Optional[dict[str, Any]]:
    """Reassemble the full snapshot dict, or None if nothing stored yet."""
    conn = _conn()

    meta_rows = conn.execute("SELECT key, value FROM meta").fetchall()
    if not meta_rows:
        return None
    meta = {row["key"]: row["value"] for row in meta_rows}

    network_rows = conn.execute(
        "SELECT id, name, product_types FROM networks"
    ).fetchall()
    networks = [
        {
            "id": row["id"],
            "name": row["name"],
            "productTypes": json.loads(row["product_types"]),
        }
        for row in network_rows
    ]

    topology_rows = conn.execute(
        "SELECT cache_key, payload FROM topology_cache"
    ).fetchall()
    topology = {row["cache_key"]: json.loads(row["payload"]) for row in topology_rows}

    # If the only rows we have are meta and nothing else, treat as empty.
    if not networks and not topology:
        return None

    return {
        "version": int(meta["schema_version"]) if meta.get("schema_version") else None,
        "orgName": meta.get("orgName"),
        "networks": networks,
        "selectedNetwork": meta.get("selectedNetwork"),
        "topology": topology,
        "lastUpdated": meta.get("lastUpdated"),
    }
