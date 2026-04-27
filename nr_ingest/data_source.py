"""Load the cached Meraki topology snapshot from the project's SQLite DB.

Prefers the live container DB (topologymaps-server-1:/app/data/app.db) via
docker cp so ingest always sees the latest snapshot.  Falls back to the local
data/app.db if Docker is unavailable.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
_LOCAL_DB = PROJECT_ROOT / "data" / "app.db"
_CONTAINER = "topologymaps-server-1"
_CONTAINER_DB = "/app/data/app.db"

sys.path.insert(0, str(PROJECT_ROOT / "server"))

import db  # noqa: E402


def _resolve_db_path() -> Path:
    """Return the path to a readable app.db, preferring the container's copy."""
    tmp = Path(tempfile.mktemp(suffix=".db"))
    try:
        result = subprocess.run(
            ["docker", "cp", f"{_CONTAINER}:{_CONTAINER_DB}", str(tmp)],
            capture_output=True, timeout=10,
        )
        if result.returncode == 0 and tmp.exists():
            print(f"Using DB copied from container {_CONTAINER}:{_CONTAINER_DB}")
            return tmp
    except Exception:
        pass
    print(f"Container unavailable — using local DB at {_LOCAL_DB}")
    return _LOCAL_DB


def load_snapshot() -> dict:
    """Return the full topology snapshot or raise if the cache is empty."""
    db.DB_PATH = _resolve_db_path()
    db._connection = None  # force re-open against the new path
    db.init_db()
    snapshot = db.load_snapshot()
    if snapshot is None:
        raise RuntimeError(
            "SQLite topology cache is empty. "
            "Populate it via the server UI (refresh topology) before running ingest."
        )
    return snapshot
