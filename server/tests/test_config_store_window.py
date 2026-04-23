# server/tests/test_config_store_window.py
import tempfile, pytest
from pathlib import Path

@pytest.fixture
def conn(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "topology.db"
        from server import database
        monkeypatch.setattr(database, "DB_PATH", db_path)
        c = database.get_connection()
        yield c
        c.close()

def _insert_obs(conn, *, org_id, entity_type, entity_id, config_area, hash_hex, observed_at, source_event="baseline"):
    from server.config_collector.store import upsert_blob, insert_observation_if_changed
    upsert_blob(conn, hash_hex, '{"x":1}', 7)
    conn.execute(
        """INSERT INTO config_observations
           (org_id, entity_type, entity_id, config_area, sub_key, hash, observed_at, source_event)
           VALUES (?,?,?,?,?,?,?,?)""",
        (org_id, entity_type, entity_id, config_area, "", hash_hex, observed_at, source_event)
    )
    conn.commit()

def test_window_returns_pair_when_both_exist(conn):
    from server.config_collector.store import get_observations_in_window
    _insert_obs(conn, org_id="O1", entity_type="network", entity_id="N1",
                config_area="appliance_vlans", hash_hex="aaa", observed_at="2026-04-01T00:00:00Z")
    _insert_obs(conn, org_id="O1", entity_type="network", entity_id="N1",
                config_area="appliance_vlans", hash_hex="bbb", observed_at="2026-04-20T00:00:00Z")
    pairs = get_observations_in_window(conn, org_id="O1",
                                       from_ts="2026-04-10T00:00:00Z",
                                       to_ts="2026-04-23T00:00:00Z")
    assert len(pairs) == 1
    p = pairs[0]
    assert p["from_hash"] == "aaa"
    assert p["to_hash"] == "bbb"
    assert p["entity_id"] == "N1"
    assert p["config_area"] == "appliance_vlans"

def test_window_returns_none_from_when_only_to_exists(conn):
    from server.config_collector.store import get_observations_in_window
    _insert_obs(conn, org_id="O1", entity_type="network", entity_id="N2",
                config_area="appliance_vlans", hash_hex="ccc", observed_at="2026-04-20T00:00:00Z")
    pairs = get_observations_in_window(conn, org_id="O1",
                                       from_ts="2026-04-10T00:00:00Z",
                                       to_ts="2026-04-23T00:00:00Z")
    assert len(pairs) == 1
    assert pairs[0]["from_hash"] is None
    assert pairs[0]["to_hash"] == "ccc"

def test_window_excludes_pairs_with_identical_hashes(conn):
    from server.config_collector.store import get_observations_in_window
    _insert_obs(conn, org_id="O1", entity_type="network", entity_id="N3",
                config_area="appliance_vlans", hash_hex="same", observed_at="2026-04-01T00:00:00Z")
    _insert_obs(conn, org_id="O1", entity_type="network", entity_id="N3",
                config_area="appliance_vlans", hash_hex="same", observed_at="2026-04-20T00:00:00Z")
    pairs = get_observations_in_window(conn, org_id="O1",
                                       from_ts="2026-04-10T00:00:00Z",
                                       to_ts="2026-04-23T00:00:00Z")
    assert pairs == []

def test_window_returns_empty_when_nothing_in_range(conn):
    from server.config_collector.store import get_observations_in_window
    pairs = get_observations_in_window(conn, org_id="O1",
                                       from_ts="2026-04-10T00:00:00Z",
                                       to_ts="2026-04-23T00:00:00Z")
    assert pairs == []

def test_window_handles_null_sub_key(conn):
    from server.config_collector.store import get_observations_in_window
    from server.config_collector.store import upsert_blob
    upsert_blob(conn, "h1", '{"x":1}', 7)
    upsert_blob(conn, "h2", '{"x":2}', 7)
    conn.execute(
        "INSERT INTO config_observations (org_id,entity_type,entity_id,config_area,sub_key,hash,observed_at,source_event) VALUES (?,?,?,?,?,?,?,?)",
        ("O1","network","N9","appliance_settings",None,"h1","2026-04-01T00:00:00Z","baseline")
    )
    conn.execute(
        "INSERT INTO config_observations (org_id,entity_type,entity_id,config_area,sub_key,hash,observed_at,source_event) VALUES (?,?,?,?,?,?,?,?)",
        ("O1","network","N9","appliance_settings",None,"h2","2026-04-20T00:00:00Z","change_log")
    )
    conn.commit()
    pairs = get_observations_in_window(conn, org_id="O1",
                                       from_ts="2026-04-10T00:00:00Z",
                                       to_ts="2026-04-23T00:00:00Z")
    assert len(pairs) == 1
    assert pairs[0]["from_hash"] == "h1"
    assert pairs[0]["to_hash"] == "h2"
