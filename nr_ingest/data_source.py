"""Load the cached Meraki topology snapshot from the project's SQLite DB."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "server"))

import db  # noqa: E402


def load_snapshot() -> dict:
    """Return the full topology snapshot or raise if the cache is empty."""
    snapshot = db.load_snapshot()
    if snapshot is None:
        raise RuntimeError(
            "SQLite topology cache is empty. "
            "Populate it via the server UI (refresh topology) before running ingest."
        )
    return snapshot
