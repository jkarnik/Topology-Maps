# server/tests/test_config_api_diff.py
import tempfile, pytest, json
from pathlib import Path
from fastapi.testclient import TestClient

@pytest.fixture
def app(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "topology.db"
        from server import database
        monkeypatch.setattr(database, "DB_PATH", db_path)
        database.get_connection().close()
        from server.main import app
        yield app

@pytest.fixture
def client(app):
    return TestClient(app)

def _seed_two_obs(conn, hash_a="aaa", hash_b="bbb"):
    from server.config_collector.store import upsert_blob
    upsert_blob(conn, hash_a, json.dumps({"vlan": 10}), 10)
    upsert_blob(conn, hash_b, json.dumps({"vlan": 20}), 10)
    conn.execute(
        "INSERT INTO config_observations (org_id,entity_type,entity_id,config_area,sub_key,hash,observed_at,source_event) VALUES (?,?,?,?,?,?,?,?)",
        ("O1","network","N1","appliance_settings","",hash_a,"2026-04-01T00:00:00Z","baseline")
    )
    conn.execute(
        "INSERT INTO config_observations (org_id,entity_type,entity_id,config_area,sub_key,hash,observed_at,source_event) VALUES (?,?,?,?,?,?,?,?)",
        ("O1","network","N1","appliance_settings","",hash_b,"2026-04-20T00:00:00Z","change_log")
    )
    conn.commit()

def test_org_diff_returns_changes(app, client, monkeypatch):
    from server import database
    conn = database.get_connection()
    _seed_two_obs(conn)
    conn.close()
    resp = client.get("/api/config/diff/org", params={
        "org_id": "O1",
        "from_ts": "2026-04-10T00:00:00Z",
        "to_ts": "2026-04-23T00:00:00Z",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["changed_count"] == 1
    assert len(body["results"]) == 1
    r = body["results"][0]
    assert r["entity_id"] == "N1"
    assert r["config_area"] == "appliance_settings"
    assert r["diff"]["shape"] == "object"
    assert len(r["diff"]["changes"]) == 1

def test_org_diff_empty_range(client):
    resp = client.get("/api/config/diff/org", params={
        "org_id": "O1",
        "from_ts": "2026-04-10T00:00:00Z",
        "to_ts": "2026-04-23T00:00:00Z",
    })
    assert resp.status_code == 200
    assert resp.json()["changed_count"] == 0
    assert resp.json()["results"] == []

def test_org_diff_missing_org_id(client):
    resp = client.get("/api/config/diff/org", params={
        "from_ts": "2026-04-10T00:00:00Z",
        "to_ts": "2026-04-23T00:00:00Z",
    })
    assert resp.status_code == 422
