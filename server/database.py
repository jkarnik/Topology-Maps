"""SQLite persistence for topology state and connection history."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "topology.db"


def get_connection() -> sqlite3.Connection:
    """Get a SQLite connection, creating the database and tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _create_tables(conn)
    return conn


def _create_tables(conn: sqlite3.Connection) -> None:
    """Create database tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS devices (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            model TEXT NOT NULL,
            ip TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'up',
            floor INTEGER,
            category TEXT,
            mac TEXT,
            vlan INTEGER,
            data_json TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS edges (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            source_port TEXT,
            target_port TEXT,
            speed TEXT DEFAULT '1G',
            protocol TEXT DEFAULT 'LLDP',
            updated_at TEXT NOT NULL,
            FOREIGN KEY (source) REFERENCES devices(id),
            FOREIGN KEY (target) REFERENCES devices(id)
        );

        CREATE TABLE IF NOT EXISTS topology_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_type TEXT NOT NULL,  -- 'l2' or 'l3'
            data_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS connection_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,  -- 'move', 'create', 'delete'
            device TEXT NOT NULL,
            from_switch TEXT,
            from_port INTEGER,
            to_switch TEXT,
            to_port INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'applied', 'failed'
            created_at TEXT NOT NULL,
            applied_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source);
        CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target);
        CREATE INDEX IF NOT EXISTS idx_devices_type ON devices(type);
        CREATE INDEX IF NOT EXISTS idx_connection_history_device ON connection_history(device);
    """)
    conn.commit()


def save_device(conn: sqlite3.Connection, device: dict) -> None:
    """Insert or update a device record."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT OR REPLACE INTO devices (id, type, model, ip, status, floor, category, mac, vlan, data_json, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            device["id"],
            device["type"],
            device["model"],
            device["ip"],
            device.get("status", "up"),
            device.get("floor"),
            device.get("category"),
            device.get("mac"),
            device.get("vlan"),
            json.dumps(device),
            now,
        ),
    )
    conn.commit()


def save_edge(conn: sqlite3.Connection, edge: dict) -> None:
    """Insert or update an edge record."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT OR REPLACE INTO edges (id, source, target, source_port, target_port, speed, protocol, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            edge["id"],
            edge["source"],
            edge["target"],
            edge.get("source_port"),
            edge.get("target_port"),
            edge.get("speed", "1G"),
            edge.get("protocol", "LLDP"),
            now,
        ),
    )
    conn.commit()


def save_topology_snapshot(conn: sqlite3.Connection, snapshot_type: str, data: dict) -> int:
    """Save a topology snapshot. Returns the snapshot ID."""
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "INSERT INTO topology_snapshots (snapshot_type, data_json, created_at) VALUES (?, ?, ?)",
        (snapshot_type, json.dumps(data), now),
    )
    conn.commit()
    return cursor.lastrowid


def get_latest_snapshot(conn: sqlite3.Connection, snapshot_type: str) -> Optional[dict]:
    """Get the most recent topology snapshot of the given type."""
    row = conn.execute(
        "SELECT data_json FROM topology_snapshots WHERE snapshot_type = ? ORDER BY id DESC LIMIT 1",
        (snapshot_type,),
    ).fetchone()
    if row:
        return json.loads(row["data_json"])
    return None


def log_connection_edit(conn: sqlite3.Connection, edit: dict) -> int:
    """Log a connection edit to history. Returns the history ID."""
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        """INSERT INTO connection_history (action, device, from_switch, from_port, to_switch, to_port, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
        (
            edit["action"],
            edit["device"],
            edit.get("from", {}).get("switch") if edit.get("from") else None,
            edit.get("from", {}).get("port") if edit.get("from") else None,
            edit.get("to", {}).get("switch") if edit.get("to") else None,
            edit.get("to", {}).get("port") if edit.get("to") else None,
            now,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def mark_connection_applied(conn: sqlite3.Connection, history_id: int) -> None:
    """Mark a connection edit as applied."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE connection_history SET status = 'applied', applied_at = ? WHERE id = ?",
        (now, history_id),
    )
    conn.commit()


def get_all_devices(conn: sqlite3.Connection) -> list[dict]:
    """Get all devices."""
    rows = conn.execute("SELECT data_json FROM devices").fetchall()
    return [json.loads(row["data_json"]) for row in rows]


def get_all_edges(conn: sqlite3.Connection) -> list[dict]:
    """Get all edges."""
    rows = conn.execute("SELECT * FROM edges").fetchall()
    return [dict(row) for row in rows]
