"""Load the Meraki config history from the project's topology SQLite DB.

Prefers the live container DB (topologymaps-server-1:/app/data/topology.db) via
docker cp so ingest always sees the latest config observations.  Falls back to
the local data/topology.db if Docker is unavailable.
"""
from __future__ import annotations
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
_LOCAL_TOPOLOGY_DB = PROJECT_ROOT / "data" / "topology.db"
_CONTAINER = "topologymaps-server-1"
_CONTAINER_DB = "/app/data/topology.db"


def _resolve_topology_db_path() -> Path:
    """Return the path to a readable topology.db, preferring the container's copy."""
    tmp_fd, tmp_str = tempfile.mkstemp(suffix=".db")
    os.close(tmp_fd)
    tmp = Path(tmp_str)
    try:
        result = subprocess.run(
            ["docker", "cp", f"{_CONTAINER}:{_CONTAINER_DB}", str(tmp)],
            capture_output=True, timeout=10,
        )
        if result.returncode == 0 and tmp.exists():
            print(f"Using topology.db copied from {_CONTAINER}:{_CONTAINER_DB}")
            return tmp
    except Exception:
        pass
    print(f"Container unavailable — using local {_LOCAL_TOPOLOGY_DB}")
    return _LOCAL_TOPOLOGY_DB


def load_config_db() -> sqlite3.Connection:
    """Open and return a connection to the topology config DB."""
    path = _resolve_topology_db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
