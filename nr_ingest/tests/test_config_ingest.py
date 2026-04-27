from __future__ import annotations
import sqlite3
import subprocess
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "server"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from config_data_source import load_config_db
import config_data_source as _cds


def test_load_config_db_local_fallback(tmp_path, monkeypatch):
    db_path = tmp_path / "topology.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE config_observations (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: type("R", (), {"returncode": 1})())
    monkeypatch.setattr(_cds, "_LOCAL_TOPOLOGY_DB", db_path)

    conn = load_config_db()
    assert conn is not None
    conn.close()
