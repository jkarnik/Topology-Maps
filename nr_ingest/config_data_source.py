"""Load the Meraki config history from the project's topology SQLite DB.

Prefers the live container DB (topologymaps-server-1:/app/data/topology.db) via
docker cp so ingest always sees the latest config observations.  Falls back to
the local data/topology.db if Docker is unavailable.
"""
from __future__ import annotations
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_STALE_THRESHOLD_SECONDS = 24 * 3600

PROJECT_ROOT = Path(__file__).parent.parent
_LOCAL_TOPOLOGY_DB = PROJECT_ROOT / "data" / "topology.db"
_CONTAINER = "topologymaps-server-1"
_CONTAINER_DB = "/app/data/topology.db"


def _resolve_topology_db_path() -> Path:
    """Return the path to a readable topology.db, preferring the container's copy.

    Copies both the main DB file and the WAL file so that SQLite sees all
    uncommitted writes that haven't been checkpointed yet.
    """
    tmp_fd, tmp_str = tempfile.mkstemp(suffix=".db")
    os.close(tmp_fd)
    tmp = Path(tmp_str)
    try:
        result = subprocess.run(
            ["docker", "cp", f"{_CONTAINER}:{_CONTAINER_DB}", str(tmp)],
            capture_output=True, timeout=10,
        )
        if result.returncode == 0 and tmp.exists():
            # Also copy the WAL file if it exists so SQLite sees all recent writes.
            wal_src = _CONTAINER_DB + "-wal"
            wal_dst = Path(str(tmp) + "-wal")
            subprocess.run(
                ["docker", "cp", f"{_CONTAINER}:{wal_src}", str(wal_dst)],
                capture_output=True, timeout=10,
            )
            print(f"Using topology.db copied from {_CONTAINER}:{_CONTAINER_DB}")
            return tmp
    except Exception:
        pass
    if not _LOCAL_TOPOLOGY_DB.exists():
        print(f"ERROR: Container unavailable and no local DB found at {_LOCAL_TOPOLOGY_DB}. Is Docker running?", file=sys.stderr)
        sys.exit(1)
    age = time.time() - _LOCAL_TOPOLOGY_DB.stat().st_mtime
    if age > _STALE_THRESHOLD_SECONDS:
        hours = age / 3600
        print(
            f"ERROR: Container unavailable and local DB is {hours:.1f}h old (threshold: 24h). "
            f"Start Docker and re-run, or the data pushed to NR will be stale.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"WARNING: Container unavailable — using local {_LOCAL_TOPOLOGY_DB} ({age/3600:.1f}h old)")
    return _LOCAL_TOPOLOGY_DB


def load_config_db() -> sqlite3.Connection:
    """Open and return a connection to the topology config DB."""
    path = _resolve_topology_db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
