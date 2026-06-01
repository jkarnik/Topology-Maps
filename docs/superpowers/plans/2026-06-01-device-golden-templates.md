# Device Golden Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow Gateway, Switch, and Access Point templates to be promoted from a specific device's config (entity_type='device') rather than a network's config, with scoring grouped by network showing individual device compliance.

**Architecture:** DB migration adds two nullable columns to `config_templates`; `store.py` branches on `device_serial` presence to query device vs network observations; the scoring endpoint detects device templates and returns a new `networks`-keyed response shape; the frontend adds a two-step promote modal and a grouped scoring panel.

**Tech Stack:** Python/FastAPI, SQLite, React/TypeScript, Tailwind

---

## File Map

| File | Change |
|---|---|
| `server/database.py` | Add migration for `source_device_serial`, `source_device_name` columns |
| `server/config_collector/store.py` | Update `create_template`; add `list_devices_for_kind` |
| `server/routes/config.py` | Add `GET /devices-for-template`; update `POST /templates`; update scores endpoint |
| `server/tests/test_config_store_templates.py` | Tests for device template creation |
| `server/tests/test_config_api_compare.py` | Tests for new endpoint + device scoring |
| `ui/src/types/config.ts` | New device score types; update `ConfigTemplate` |
| `ui/src/api/compare.ts` | Update `createTemplate`; add `listDevicesForTemplate` |
| `ui/src/hooks/useTemplates.ts` | Update `promote` signature |
| `ui/src/hooks/useDevicesForTemplate.ts` | New hook |
| `ui/src/components/ConfigBrowser/TemplatesView.tsx` | Update `PromoteModal`; update `ScoresPanel` |

---

### Task 1: DB migration — add device columns to config_templates

**Files:**
- Modify: `server/database.py`

- [ ] **Step 1: Update `_run_migrations` to handle all three new columns**

In `server/database.py`, replace the existing `_run_migrations` function body:

```python
def _run_migrations(conn: sqlite3.Connection) -> None:
    for ddl in [
        "ALTER TABLE config_templates ADD COLUMN kind TEXT",
        "ALTER TABLE config_templates ADD COLUMN source_device_serial TEXT",
        "ALTER TABLE config_templates ADD COLUMN source_device_name TEXT",
    ]:
        try:
            conn.execute(ddl)
            conn.commit()
        except Exception:
            pass  # column already exists
```

- [ ] **Step 2: Verify migration runs without error**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
python3 -c "from server.database import get_connection; c = get_connection(); print([r[1] for r in c.execute('PRAGMA table_info(config_templates)').fetchall()])"
```

Expected output includes: `'kind', 'source_device_serial', 'source_device_name'`

- [ ] **Step 3: Commit**

```bash
git add server/database.py
git commit -m "feat: add source_device_serial/name columns to config_templates"
```

---

### Task 2: store.py — update create_template for device promotion

**Files:**
- Modify: `server/config_collector/store.py`
- Test: `server/tests/test_config_store_templates.py`

- [ ] **Step 1: Write the failing tests**

Add to the end of `server/tests/test_config_store_templates.py`:

```python
def _seed_device_observation(conn, org_id, serial, config_area, blob_hash, name=None):
    store.insert_observation_if_changed(
        conn,
        org_id=org_id,
        entity_type="device",
        entity_id=serial,
        config_area=config_area,
        sub_key=None,
        hash_hex=blob_hash,
        source_event="baseline",
        change_event_id=None,
        sweep_run_id=None,
        hot_columns={"name_hint": name} if name else {},
    )


def test_create_device_template(conn):
    h = _seed_blob(conn, '{"ports": [{"id": 1}]}')
    _seed_device_observation(conn, "org1", "Q2SW-0001", "switch_device_ports", h, name="Core-SW-01")

    tmpl = store.create_template(
        conn,
        org_id="org1",
        name="Standard Core Switch",
        network_id="net1",
        network_name=None,
        kind="switch",
        device_serial="Q2SW-0001",
        device_name="Core-SW-01",
    )

    assert tmpl["source_device_serial"] == "Q2SW-0001"
    assert tmpl["source_device_name"] == "Core-SW-01"
    assert len(tmpl["areas"]) == 1
    assert tmpl["areas"][0]["config_area"] == "switch_device_ports"


def test_device_template_excludes_network_areas(conn):
    h_net = _seed_blob(conn, '{"ssids": []}')
    h_dev = _seed_blob(conn, '{"ports": []}')
    _seed_observation(conn, "org1", "net1", "wireless_ssids", h_net)
    _seed_device_observation(conn, "org1", "Q2SW-0001", "switch_device_ports", h_dev)

    tmpl = store.create_template(
        conn,
        org_id="org1",
        name="Switch Template",
        network_id="net1",
        network_name="Store 1",
        kind="switch",
        device_serial="Q2SW-0001",
        device_name="Core-SW-01",
    )

    area_names = [a["config_area"] for a in tmpl["areas"]]
    assert "switch_device_ports" in area_names
    assert "wireless_ssids" not in area_names
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
python3 -m pytest server/tests/test_config_store_templates.py::test_create_device_template -v
```

Expected: FAIL — `create_template() got unexpected keyword argument 'device_serial'`

- [ ] **Step 3: Update `create_template` in store.py**

Replace the existing `create_template` function (lines ~372–416):

```python
def create_template(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    name: str,
    network_id: str,
    network_name: Optional[str],
    kind: Optional[str] = None,
    device_serial: Optional[str] = None,
    device_name: Optional[str] = None,
) -> dict:
    """Promote a network or device snapshot to a template. Returns the full template dict."""
    now = _now_iso()
    cursor = conn.execute(
        """INSERT INTO config_templates
               (org_id, name, source_network_id, source_network_name, created_at, kind,
                source_device_serial, source_device_name)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (org_id, name, network_id, network_name, now, kind, device_serial, device_name),
    )
    template_id = cursor.lastrowid

    if device_serial:
        rows = conn.execute(
            """SELECT config_area, sub_key, hash
               FROM config_observations
               WHERE org_id=? AND entity_type='device' AND entity_id=?
               GROUP BY config_area, sub_key
               HAVING MAX(observed_at)""",
            (org_id, device_serial),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT config_area, sub_key, hash
               FROM config_observations
               WHERE org_id=? AND entity_type='network' AND entity_id=?
               GROUP BY config_area, sub_key
               HAVING MAX(observed_at)""",
            (org_id, network_id),
        ).fetchall()

    areas = []
    for row in rows:
        conn.execute(
            """INSERT INTO config_template_areas (template_id, config_area, sub_key, blob_hash)
               VALUES (?, ?, ?, ?)""",
            (template_id, row["config_area"], row["sub_key"], row["hash"]),
        )
        areas.append({"config_area": row["config_area"], "sub_key": row["sub_key"], "blob_hash": row["hash"]})

    conn.commit()
    return {
        "id": template_id,
        "org_id": org_id,
        "name": name,
        "source_network_id": network_id,
        "source_network_name": network_name,
        "created_at": now,
        "kind": kind,
        "source_device_serial": device_serial,
        "source_device_name": device_name,
        "areas": areas,
    }
```

- [ ] **Step 4: Run all template store tests**

```bash
python3 -m pytest server/tests/test_config_store_templates.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add server/config_collector/store.py server/tests/test_config_store_templates.py
git commit -m "feat: update create_template to support device-scope promotion"
```

---

### Task 3: store.py — add list_devices_for_kind

**Files:**
- Modify: `server/config_collector/store.py`
- Test: `server/tests/test_config_store_templates.py`

- [ ] **Step 1: Write the failing test**

Add to `server/tests/test_config_store_templates.py`:

```python
def test_list_devices_for_kind(conn):
    h = _seed_blob(conn)
    _seed_device_observation(conn, "org1", "Q2SW-0001", "switch_device_ports", h, name="Core-SW-01")
    _seed_device_observation(conn, "org1", "Q2SW-0002", "switch_device_ports", h, name="Floor-SW-02")
    # AP device — should NOT appear for switch kind
    _seed_device_observation(conn, "org1", "Q2MR-0001", "wireless_device_radio_settings", h, name="AP-01")

    devices = store.list_devices_for_kind(
        conn,
        org_id="org1",
        serials=["Q2SW-0001", "Q2SW-0002", "Q2MR-0001"],
        kind="switch",
    )

    serials = [d["serial"] for d in devices]
    assert "Q2SW-0001" in serials
    assert "Q2SW-0002" in serials
    assert "Q2MR-0001" not in serials


def test_list_devices_for_kind_empty_serials(conn):
    devices = store.list_devices_for_kind(conn, org_id="org1", serials=[], kind="switch")
    assert devices == []
```

- [ ] **Step 2: Run to verify failure**

```bash
python3 -m pytest server/tests/test_config_store_templates.py::test_list_devices_for_kind -v
```

Expected: FAIL — `AttributeError: module has no attribute 'list_devices_for_kind'`

- [ ] **Step 3: Implement `list_devices_for_kind` and `_KIND_AREA_PREFIX` in store.py**

Add after the `delete_template` function (after line ~448):

```python
_KIND_AREA_PREFIX: dict[str, str] = {
    "gateway":      "appliance_device_",
    "switch":       "switch_device_",
    "access_point": "wireless_device_",
}


def list_devices_for_kind(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    serials: list[str],
    kind: str,
) -> list[dict]:
    """Return serials (from the given list) that have device-scope observations for kind."""
    prefix = _KIND_AREA_PREFIX.get(kind)
    if not prefix or not serials:
        return []
    placeholders = ",".join("?" * len(serials))
    rows = conn.execute(
        f"""SELECT entity_id, MAX(name_hint) AS name
            FROM config_observations
            WHERE org_id=? AND entity_type='device'
              AND entity_id IN ({placeholders})
              AND config_area LIKE ?
            GROUP BY entity_id""",
        [org_id, *serials, f"{prefix}%"],
    ).fetchall()
    return [{"serial": r["entity_id"], "name": r["name"]} for r in rows]
```

- [ ] **Step 4: Run all template store tests**

```bash
python3 -m pytest server/tests/test_config_store_templates.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add server/config_collector/store.py server/tests/test_config_store_templates.py
git commit -m "feat: add list_devices_for_kind store function"
```

---

### Task 4: routes/config.py — new devices-for-template endpoint

**Files:**
- Modify: `server/routes/config.py`
- Test: `server/tests/test_config_api_compare.py`

- [ ] **Step 1: Write the failing test**

Add to `server/tests/test_config_api_compare.py`:

```python
def test_devices_for_template_no_meraki(client, monkeypatch, tmp_path):
    """With Meraki unconfigured, falls back to all org devices of matching kind."""
    db_path = tmp_path / "topology.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    conn = database.get_connection()
    import hashlib, json as j
    payload = j.dumps({"ports": []})
    h = hashlib.sha256(payload.encode()).hexdigest()
    store.upsert_blob(conn, h, payload, len(payload))
    store.insert_observation_if_changed(
        conn, org_id="org1", entity_type="device", entity_id="Q2SW-0001",
        config_area="switch_device_ports", sub_key=None, hash_hex=h,
        source_event="baseline", change_event_id=None, sweep_run_id=None,
        hot_columns={"name_hint": "Core-SW-01"},
    )
    conn.close()

    resp = client.get("/api/config/devices-for-template?org_id=org1&network_id=net1&kind=switch")
    assert resp.status_code == 200
    data = resp.json()
    serials = [d["serial"] for d in data["devices"]]
    assert "Q2SW-0001" in serials
    assert data["network_filter_unavailable"] is True
```

- [ ] **Step 2: Run to verify failure**

```bash
python3 -m pytest server/tests/test_config_api_compare.py::test_devices_for_template_no_meraki -v
```

Expected: FAIL — 404 or route not found.

- [ ] **Step 3: Add import and new endpoint to routes/config.py**

First update the store imports at the top of `server/routes/config.py` (around line 23):

```python
from server.config_collector.store import (
    get_latest_observation, get_observation_history,
    get_blob_by_hash, get_change_events,
    create_sweep_run, get_active_sweep_run,
    get_observations_in_window,
    create_template, list_templates, get_template_areas,
    delete_template, get_coverage, list_devices_for_kind,
)
```

Then add the new endpoint after the `delete_template_route` (after line ~560):

```python
@router.get("/devices-for-template")
async def list_devices_for_template(org_id: str, network_id: str, kind: str) -> dict:
    """Return devices of the matching kind observed in the given network."""
    conn = get_connection()
    try:
        network_filter_unavailable = False
        serials_in_network: list[str] | None = None

        client = _get_meraki_client()
        if client.is_configured:
            try:
                inventory = await client.get_org_inventory_devices(org_id)
                serials_in_network = [
                    d["serial"] for d in inventory
                    if d.get("networkId") == network_id and d.get("serial")
                ]
            except Exception as exc:
                logger.warning("devices-for-template: Meraki inventory failed: %s", exc)
                network_filter_unavailable = True
        else:
            network_filter_unavailable = True

        if serials_in_network is not None:
            devices = list_devices_for_kind(conn, org_id=org_id, serials=serials_in_network, kind=kind)
        else:
            # Fallback: return all observed devices of this kind (no network filter)
            all_device_rows = conn.execute(
                "SELECT DISTINCT entity_id FROM config_observations WHERE org_id=? AND entity_type='device'",
                (org_id,),
            ).fetchall()
            all_serials = [r["entity_id"] for r in all_device_rows]
            devices = list_devices_for_kind(conn, org_id=org_id, serials=all_serials, kind=kind)

        return {"devices": devices, "network_filter_unavailable": network_filter_unavailable}
    finally:
        conn.close()
```

- [ ] **Step 4: Run test**

```bash
python3 -m pytest server/tests/test_config_api_compare.py::test_devices_for_template_no_meraki -v
```

Expected: PASS.

- [ ] **Step 5: Run full test suite**

```bash
python3 -m pytest server/tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add server/routes/config.py server/tests/test_config_api_compare.py
git commit -m "feat: add GET /api/config/devices-for-template endpoint"
```

---

### Task 5: routes/config.py — update POST /templates to accept device_serial

**Files:**
- Modify: `server/routes/config.py`
- Test: `server/tests/test_config_api_compare.py`

- [ ] **Step 1: Write the failing test**

Add to `server/tests/test_config_api_compare.py`:

```python
def test_create_device_template_via_api(client, monkeypatch, tmp_path):
    db_path = tmp_path / "topology.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    conn = database.get_connection()
    import hashlib, json as j
    payload = j.dumps({"ports": [{"id": 1}]})
    h = hashlib.sha256(payload.encode()).hexdigest()
    store.upsert_blob(conn, h, payload, len(payload))
    store.insert_observation_if_changed(
        conn, org_id="org1", entity_type="device", entity_id="Q2SW-0001",
        config_area="switch_device_ports", sub_key=None, hash_hex=h,
        source_event="baseline", change_event_id=None, sweep_run_id=None,
        hot_columns={"name_hint": "Core-SW-01"},
    )
    conn.close()

    resp = client.post("/api/config/templates", json={
        "org_id": "org1",
        "name": "Standard Switch",
        "network_id": "net1",
        "kind": "switch",
        "device_serial": "Q2SW-0001",
        "device_name": "Core-SW-01",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_device_serial"] == "Q2SW-0001"
    assert data["source_device_name"] == "Core-SW-01"
    assert any(a["config_area"] == "switch_device_ports" for a in data["areas"])
```

- [ ] **Step 2: Run to verify failure**

```bash
python3 -m pytest server/tests/test_config_api_compare.py::test_create_device_template_via_api -v
```

Expected: FAIL — validation error (unexpected fields).

- [ ] **Step 3: Update `PromoteTemplateRequest` and `create_template_route`**

In `server/routes/config.py`, replace the `PromoteTemplateRequest` class:

```python
class PromoteTemplateRequest(BaseModel):
    org_id: str
    name: str
    network_id: str
    kind: str | None = None
    device_serial: str | None = None
    device_name: str | None = None
```

Replace the `create_template_route` body:

```python
@router.post("/templates")
async def create_template_route(req: PromoteTemplateRequest) -> dict:
    conn = get_connection()
    try:
        network_name = None
        if not req.device_serial:
            name_row = conn.execute(
                """SELECT name_hint FROM config_observations
                   WHERE org_id=? AND entity_type='network' AND entity_id=?
                   AND name_hint IS NOT NULL ORDER BY observed_at DESC LIMIT 1""",
                (req.org_id, req.network_id),
            ).fetchone()
            network_name = name_row["name_hint"] if name_row else None
        return create_template(
            conn,
            org_id=req.org_id,
            name=req.name,
            network_id=req.network_id,
            network_name=network_name,
            kind=req.kind,
            device_serial=req.device_serial,
            device_name=req.device_name,
        )
    finally:
        conn.close()
```

- [ ] **Step 4: Run all API tests**

```bash
python3 -m pytest server/tests/test_config_api_compare.py -v --tb=short
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add server/routes/config.py server/tests/test_config_api_compare.py
git commit -m "feat: update POST /templates to accept device_serial for device-scope templates"
```

---

### Task 6: routes/config.py — device scoring in GET /templates/{id}/scores

**Files:**
- Modify: `server/routes/config.py`
- Test: `server/tests/test_config_api_compare.py`

- [ ] **Step 1: Write the failing test**

Add to `server/tests/test_config_api_compare.py`:

```python
def test_device_template_scores(client, monkeypatch, tmp_path):
    """Device template scores return networks-keyed response with per-device scores."""
    db_path = tmp_path / "topology.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    conn = database.get_connection()
    import hashlib, json as j

    payload_gold = j.dumps({"portId": "1", "enabled": True})
    payload_drift = j.dumps({"portId": "1", "enabled": False})
    h_gold = hashlib.sha256(payload_gold.encode()).hexdigest()
    h_drift = hashlib.sha256(payload_drift.encode()).hexdigest()
    store.upsert_blob(conn, h_gold, payload_gold, len(payload_gold))
    store.upsert_blob(conn, h_drift, payload_drift, len(payload_drift))

    # Golden device
    store.insert_observation_if_changed(
        conn, org_id="org1", entity_type="device", entity_id="Q2SW-GOLD",
        config_area="switch_device_ports", sub_key=None, hash_hex=h_gold,
        source_event="baseline", change_event_id=None, sweep_run_id=None,
        hot_columns={"name_hint": "Golden-SW"},
    )
    # Another device that drifted
    store.insert_observation_if_changed(
        conn, org_id="org1", entity_type="device", entity_id="Q2SW-DRIFT",
        config_area="switch_device_ports", sub_key=None, hash_hex=h_drift,
        source_event="baseline", change_event_id=None, sweep_run_id=None,
        hot_columns={"name_hint": "Drift-SW"},
    )
    conn.close()

    # Create device template
    resp = client.post("/api/config/templates", json={
        "org_id": "org1", "name": "Golden Switch", "network_id": "net1",
        "kind": "switch", "device_serial": "Q2SW-GOLD", "device_name": "Golden-SW",
    })
    tmpl_id = resp.json()["id"]

    # Get scores
    resp = client.get(f"/api/config/templates/{tmpl_id}/scores?org_id=org1")
    assert resp.status_code == 200
    data = resp.json()

    assert "networks" in data
    assert "scores" not in data

    # Unknown-network bucket holds both devices (no Meraki configured)
    all_devices = [d for n in data["networks"] for d in n["devices"]]
    serials = [d["serial"] for d in all_devices]
    assert "Q2SW-GOLD" in serials
    assert "Q2SW-DRIFT" in serials

    gold = next(d for d in all_devices if d["serial"] == "Q2SW-GOLD")
    drift = next(d for d in all_devices if d["serial"] == "Q2SW-DRIFT")
    assert gold["score_pct"] == 100
    assert drift["score_pct"] < 100
```

- [ ] **Step 2: Run to verify failure**

```bash
python3 -m pytest server/tests/test_config_api_compare.py::test_device_template_scores -v
```

Expected: FAIL — `AssertionError: 'networks' not in data` (current endpoint returns `scores` key).

- [ ] **Step 3: Replace the scoring endpoint body in routes/config.py**

The full replacement for `get_template_scores` (lines ~657–745). Replace the entire function:

```python
@router.get("/templates/{template_id}/scores")
async def get_template_scores(template_id: int, org_id: str) -> dict:
    conn = get_connection()
    try:
        tmpl_row = conn.execute(
            "SELECT * FROM config_templates WHERE id=?", (template_id,)
        ).fetchone()
        if not tmpl_row:
            raise HTTPException(status_code=404, detail="Template not found")

        template_areas = get_template_areas(conn, template_id=template_id)
        area_count = len(template_areas)
        template_info = {
            "id": template_id,
            "name": tmpl_row["name"],
            "area_count": area_count,
            "kind": tmpl_row["kind"],
        }

        if tmpl_row["source_device_serial"]:
            return await _score_device_template(conn, org_id, template_info, template_areas)
        else:
            return _score_network_template(conn, org_id, template_info, template_areas)
    finally:
        conn.close()


def _score_network_template(conn, org_id: str, template_info: dict, template_areas: list[dict]) -> dict:
    networks = conn.execute(
        """SELECT DISTINCT entity_id, MAX(name_hint) as name_hint
           FROM config_observations
           WHERE org_id=? AND entity_type='network'
           GROUP BY entity_id""",
        (org_id,),
    ).fetchall()

    scores = []
    for net in networks:
        network_id = net["entity_id"]
        network_name = net["name_hint"] or network_id
        net_obs = conn.execute(
            """SELECT config_area, sub_key, hash FROM config_observations
               WHERE org_id=? AND entity_type='network' AND entity_id=?
               GROUP BY config_area, sub_key HAVING MAX(observed_at)""",
            (org_id, network_id),
        ).fetchall()
        net_map = {(r["config_area"], r["sub_key"]): r["hash"] for r in net_obs}

        total_fields = total_changes = 0
        missing_areas: list[str] = []
        area_scores = []
        for ta in template_areas:
            key = (ta["config_area"], ta["sub_key"])
            if key not in net_map:
                missing_areas.append(ta["config_area"])
                area_scores.append({"config_area": ta["config_area"], "score_pct": 0, "change_count": 0})
                continue
            tmpl_blob = json.loads((get_blob_by_hash(conn, ta["blob_hash"]) or {}).get("payload") or "{}")
            net_blob = json.loads((get_blob_by_hash(conn, net_map[key]) or {}).get("payload") or "{}")
            diff = compute_diff(tmpl_blob, net_blob)
            n_changes = len(diff.changes)
            n_fields = diff.unchanged_count + n_changes
            total_fields += n_fields
            total_changes += n_changes
            area_score = 100 if n_fields == 0 else round((n_fields - n_changes) / n_fields * 100)
            area_scores.append({"config_area": ta["config_area"], "score_pct": area_score, "change_count": n_changes})

        score_pct = 100 if total_fields == 0 else round((total_fields - total_changes) / total_fields * 100)
        scores.append({
            "network_id": network_id,
            "network_name": network_name,
            "score_pct": score_pct,
            "change_count": total_changes,
            "total_fields": total_fields,
            "missing_areas": missing_areas,
            "area_scores": area_scores,
        })

    scores.sort(key=lambda s: s["score_pct"])
    return {"template": template_info, "scores": scores}


async def _score_device_template(conn, org_id: str, template_info: dict, template_areas: list[dict]) -> dict:
    kind = template_info.get("kind")

    # Find all devices with observations matching the kind's area prefix
    prefix = _KIND_AREA_PREFIX_FOR_SCORING(kind)
    device_rows = conn.execute(
        """SELECT DISTINCT entity_id, MAX(name_hint) AS name
           FROM config_observations
           WHERE org_id=? AND entity_type='device' AND config_area LIKE ?
           GROUP BY entity_id""",
        (org_id, f"{prefix}%"),
    ).fetchall() if prefix else []

    all_serials = {r["entity_id"]: r["name"] or r["entity_id"] for r in device_rows}

    # Resolve device → network via Meraki inventory (best-effort)
    network_for_device: dict[str, str] = {}
    network_names: dict[str, str] = {}
    client = _get_meraki_client()
    if client.is_configured and all_serials:
        try:
            inventory = await client.get_org_inventory_devices(org_id)
            for d in inventory:
                serial = d.get("serial")
                nid = d.get("networkId")
                if serial and nid:
                    network_for_device[serial] = nid
                    if nid not in network_names:
                        network_names[nid] = d.get("networkId", nid)
                if serial and not all_serials.get(serial) and d.get("name"):
                    all_serials[serial] = d["name"]
        except Exception as exc:
            logger.warning("Device template scoring: inventory fetch failed: %s", exc)

    # Score each device
    device_scores: list[dict] = []
    for serial, dev_name in all_serials.items():
        dev_obs = conn.execute(
            """SELECT config_area, sub_key, hash FROM config_observations
               WHERE org_id=? AND entity_type='device' AND entity_id=?
               GROUP BY config_area, sub_key HAVING MAX(observed_at)""",
            (org_id, serial),
        ).fetchall()
        dev_map = {(r["config_area"], r["sub_key"]): r["hash"] for r in dev_obs}

        total_fields = total_changes = 0
        missing_areas: list[str] = []
        area_scores = []
        for ta in template_areas:
            key = (ta["config_area"], ta["sub_key"])
            if key not in dev_map:
                missing_areas.append(ta["config_area"])
                area_scores.append({"config_area": ta["config_area"], "score_pct": 0, "change_count": 0})
                continue
            tmpl_blob = json.loads((get_blob_by_hash(conn, ta["blob_hash"]) or {}).get("payload") or "{}")
            dev_blob = json.loads((get_blob_by_hash(conn, dev_map[key]) or {}).get("payload") or "{}")
            diff = compute_diff(tmpl_blob, dev_blob)
            n_changes = len(diff.changes)
            n_fields = diff.unchanged_count + n_changes
            total_fields += n_fields
            total_changes += n_changes
            area_score = 100 if n_fields == 0 else round((n_fields - n_changes) / n_fields * 100)
            area_scores.append({"config_area": ta["config_area"], "score_pct": area_score, "change_count": n_changes})

        score_pct = 100 if total_fields == 0 else round((total_fields - total_changes) / total_fields * 100)
        device_scores.append({
            "serial": serial,
            "name": dev_name,
            "network_id": network_for_device.get(serial, "__unknown__"),
            "score_pct": score_pct,
            "change_count": total_changes,
            "missing_areas": missing_areas,
            "area_scores": area_scores,
        })

    # Group by network
    nets: dict[str, list[dict]] = {}
    for ds in device_scores:
        nid = ds["network_id"]
        nets.setdefault(nid, []).append(ds)

    networks_out = []
    for nid, devices in nets.items():
        agg = round(sum(d["score_pct"] for d in devices) / len(devices)) if devices else 0
        networks_out.append({
            "network_id": nid,
            "network_name": network_names.get(nid, "Unknown network" if nid == "__unknown__" else nid),
            "aggregate_score": agg,
            "device_count": len(devices),
            "devices": sorted(devices, key=lambda d: d["score_pct"]),
        })

    networks_out.sort(key=lambda n: n["aggregate_score"])
    return {"template": template_info, "networks": networks_out}


def _KIND_AREA_PREFIX_FOR_SCORING(kind: str | None) -> str:
    return {
        "gateway": "appliance_device_",
        "switch": "switch_device_",
        "access_point": "wireless_device_",
    }.get(kind or "", "")
```

Note: also remove the old inline scoring code that was in the original `get_template_scores` body.

- [ ] **Step 4: Run scoring tests**

```bash
python3 -m pytest server/tests/test_config_api_compare.py -v --tb=short
```

Expected: all pass.

- [ ] **Step 5: Run the full test suite**

```bash
python3 -m pytest server/tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all 289+ tests pass.

- [ ] **Step 6: Commit**

```bash
git add server/routes/config.py server/tests/test_config_api_compare.py
git commit -m "feat: device template scoring grouped by network"
```

---

### Task 7: Frontend — new types in types/config.ts

**Files:**
- Modify: `ui/src/types/config.ts`

- [ ] **Step 1: Update `ConfigTemplate` and add device score types**

In `ui/src/types/config.ts`, replace the `ConfigTemplate` interface and add new types after `TemplateScoresResponse`:

```typescript
export interface ConfigTemplate {
  id: number
  org_id: string
  name: string
  source_network_id: string
  source_network_name: string | null
  source_device_serial: string | null
  source_device_name: string | null
  created_at: string
  kind: TemplateKind | null
  areas: TemplateAreaRef[]
}

export interface DeviceScore {
  serial: string
  name: string
  network_id: string
  score_pct: number
  change_count: number
  missing_areas: string[]
  area_scores: TemplateAreaScore[]
}

export interface NetworkDeviceScores {
  network_id: string
  network_name: string
  aggregate_score: number
  device_count: number
  devices: DeviceScore[]
}

export interface DeviceTemplateScoresResponse {
  template: { id: number; name: string; area_count: number; kind: TemplateKind | null }
  networks: NetworkDeviceScores[]
}
```

- [ ] **Step 2: Type-check**

```bash
cd "/Users/jkarnik/Code/Topology Maps/ui"
npx tsc --noEmit 2>&1 | grep -v "warn"
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add ui/src/types/config.ts
git commit -m "feat: add DeviceScore/NetworkDeviceScores types, update ConfigTemplate"
```

---

### Task 8: Frontend — update api/compare.ts

**Files:**
- Modify: `ui/src/api/compare.ts`

- [ ] **Step 1: Update `createTemplate` and add `listDevicesForTemplate`**

Replace the entire `ui/src/api/compare.ts` file content:

```typescript
import type {
  NetworkCompareResponse,
  CoverageResponse,
  ConfigTemplate,
  TemplateKind,
  TemplateScoresResponse,
  DeviceTemplateScoresResponse,
} from '../types/config'

const BASE = '/api/config'

async function _fetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${path}`)
  return res.json()
}

export function compareNetworks(
  orgId: string,
  networkA: string,
  networkB: string,
): Promise<NetworkCompareResponse> {
  const qs = new URLSearchParams({ org_id: orgId, network_a: networkA, network_b: networkB })
  return _fetch(`/compare/networks?${qs}`)
}

export function getCoverage(orgId: string): Promise<CoverageResponse> {
  return _fetch(`/coverage?${new URLSearchParams({ org_id: orgId })}`)
}

export function listTemplates(orgId: string): Promise<ConfigTemplate[]> {
  return _fetch(`/templates?${new URLSearchParams({ org_id: orgId })}`)
}

export function createTemplate(
  orgId: string,
  name: string,
  networkId: string,
  kind: TemplateKind | null,
  deviceSerial: string | null,
  deviceName: string | null,
): Promise<ConfigTemplate> {
  return _fetch('/templates', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      org_id: orgId,
      name,
      network_id: networkId,
      kind,
      device_serial: deviceSerial,
      device_name: deviceName,
    }),
  })
}

export function deleteTemplate(templateId: number): Promise<{ deleted: number }> {
  return _fetch(`/templates/${templateId}`, { method: 'DELETE' })
}

export function getTemplateScores(
  templateId: number,
  orgId: string,
): Promise<TemplateScoresResponse | DeviceTemplateScoresResponse> {
  return _fetch(`/templates/${templateId}/scores?${new URLSearchParams({ org_id: orgId })}`)
}

export function listDevicesForTemplate(
  orgId: string,
  networkId: string,
  kind: TemplateKind,
): Promise<{ devices: { serial: string; name: string | null }[]; network_filter_unavailable: boolean }> {
  const qs = new URLSearchParams({ org_id: orgId, network_id: networkId, kind })
  return _fetch(`/devices-for-template?${qs}`)
}
```

- [ ] **Step 2: Type-check**

```bash
cd "/Users/jkarnik/Code/Topology Maps/ui"
npx tsc --noEmit 2>&1 | grep -v "warn"
```

Expected: no errors (may have errors in consumers not yet updated — fix those in the tasks below).

- [ ] **Step 3: Commit**

```bash
git add ui/src/api/compare.ts
git commit -m "feat: update createTemplate API, add listDevicesForTemplate"
```

---

### Task 9: Frontend — update useTemplates and add useDevicesForTemplate

**Files:**
- Modify: `ui/src/hooks/useTemplates.ts`
- Create: `ui/src/hooks/useDevicesForTemplate.ts`

- [ ] **Step 1: Update `useTemplates.ts`**

Replace `ui/src/hooks/useTemplates.ts`:

```typescript
import { useState, useEffect, useCallback } from 'react'
import { listTemplates, createTemplate, deleteTemplate } from '../api/compare'
import type { ConfigTemplate, TemplateKind } from '../types/config'

export function useTemplates(orgId: string | null) {
  const [templates, setTemplates] = useState<ConfigTemplate[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(() => {
    if (!orgId) return
    setLoading(true)
    listTemplates(orgId)
      .then(t => { setTemplates(t); setLoading(false); setError(null) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [orgId])

  useEffect(() => { reload() }, [reload])

  const promote = useCallback(async (
    name: string,
    networkId: string,
    kind: TemplateKind | null,
    deviceSerial: string | null,
    deviceName: string | null,
  ) => {
    if (!orgId) return
    await createTemplate(orgId, name, networkId, kind, deviceSerial, deviceName)
    reload()
  }, [orgId, reload])

  const remove = useCallback(async (templateId: number) => {
    await deleteTemplate(templateId)
    reload()
  }, [reload])

  return { templates, loading, error, promote, remove, reload }
}
```

- [ ] **Step 2: Create `useDevicesForTemplate.ts`**

Create `ui/src/hooks/useDevicesForTemplate.ts`:

```typescript
import { useState, useEffect } from 'react'
import { listDevicesForTemplate } from '../api/compare'
import type { TemplateKind } from '../types/config'

export interface DeviceOption {
  serial: string
  name: string | null
}

export function useDevicesForTemplate(
  orgId: string | null,
  networkId: string | null,
  kind: TemplateKind | null,
) {
  const [devices, setDevices] = useState<DeviceOption[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!orgId || !networkId || !kind || kind === 'site') {
      setDevices([])
      return
    }
    setLoading(true)
    setError(null)
    listDevicesForTemplate(orgId, networkId, kind)
      .then(r => { setDevices(r.devices); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [orgId, networkId, kind])

  return { devices, loading, error }
}
```

- [ ] **Step 3: Update `useTemplateScores.ts` to handle both response shapes**

Replace `ui/src/hooks/useTemplateScores.ts`:

```typescript
import { useState, useEffect } from 'react'
import { getTemplateScores } from '../api/compare'
import type { TemplateScoresResponse, DeviceTemplateScoresResponse } from '../types/config'

export type AnyScoresResponse = TemplateScoresResponse | DeviceTemplateScoresResponse

export function isSiteScores(r: AnyScoresResponse): r is TemplateScoresResponse {
  return 'scores' in r
}

export function useTemplateScores(templateId: number | null, orgId: string | null) {
  const [data, setData] = useState<AnyScoresResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!templateId || !orgId) { setData(null); return }
    setLoading(true)
    setError(null)
    getTemplateScores(templateId, orgId)
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [templateId, orgId])

  return { data, loading, error }
}
```

- [ ] **Step 4: Type-check**

```bash
cd "/Users/jkarnik/Code/Topology Maps/ui"
npx tsc --noEmit 2>&1 | grep -v "warn"
```

Expected: any remaining errors are in TemplatesView.tsx (not yet updated) — that is fine.

- [ ] **Step 5: Commit**

```bash
git add ui/src/hooks/useTemplates.ts ui/src/hooks/useDevicesForTemplate.ts ui/src/hooks/useTemplateScores.ts
git commit -m "feat: update hooks for device template support"
```

---

### Task 10: TemplatesView.tsx — update PromoteModal for device templates

**Files:**
- Modify: `ui/src/components/ConfigBrowser/TemplatesView.tsx`

- [ ] **Step 1: Update imports at the top of TemplatesView.tsx**

Replace the import lines (lines 1–4):

```typescript
import { useState } from 'react'
import { useTemplates } from '../../hooks/useTemplates'
import { useTemplateScores, isSiteScores } from '../../hooks/useTemplateScores'
import { useDevicesForTemplate } from '../../hooks/useDevicesForTemplate'
import type {
  ConfigTemplate,
  ConfigTree,
  NetworkTemplateScore,
  TemplateKind,
  TemplateScoresResponse,
  DeviceTemplateScoresResponse,
  NetworkDeviceScores,
  DeviceScore,
} from '../../types/config'
```

- [ ] **Step 2: Replace the `PromoteModal` component**

Replace the entire `PromoteModal` function (lines ~71–98 in the current file) with:

```typescript
interface PromoteModalProps {
  orgId: string
  tree: ConfigTree | null
  onConfirm: (name: string, networkId: string, kind: TemplateKind | null, deviceSerial: string | null, deviceName: string | null) => void
  onCancel: () => void
}

function PromoteModal({ orgId, tree, onConfirm, onCancel }: PromoteModalProps) {
  const [name, setName] = useState('')
  const [networkId, setNetworkId] = useState('')
  const [kind, setKind] = useState<TemplateKind | ''>('')
  const [deviceSerial, setDeviceSerial] = useState<string | null>(null)
  const networks = tree?.networks ?? []

  const needsDevice = kind && kind !== 'site'
  const { devices, loading: devicesLoading } = useDevicesForTemplate(
    orgId,
    needsDevice ? networkId : null,
    needsDevice ? kind as TemplateKind : null,
  )

  const canSave = name.trim() && networkId && (kind === 'site' || !needsDevice || deviceSerial)

  const selectedDevice = devices.find(d => d.serial === deviceSerial) ?? null

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-[#1a1a2e] border border-white/10 rounded-lg p-5 w-80 space-y-3">
        <h3 className="text-sm font-medium">Promote as Golden Template</h3>

        <div>
          <label className="text-xs opacity-50 block mb-1">Template type</label>
          <select
            value={kind}
            onChange={e => { setKind(e.target.value as TemplateKind | ''); setDeviceSerial(null) }}
            className="w-full bg-white/5 border border-white/10 rounded px-2 py-1.5 text-xs"
          >
            <option value="">Select a type…</option>
            {KIND_ORDER.map(k => (
              <option key={k} value={k}>{KIND_META[k].label}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-xs opacity-50 block mb-1">{needsDevice ? 'Step 1 — Pick a network' : 'Network'}</label>
          <select
            value={networkId}
            onChange={e => { setNetworkId(e.target.value); setDeviceSerial(null) }}
            className="w-full bg-white/5 border border-white/10 rounded px-2 py-1.5 text-xs"
          >
            <option value="">Select a network…</option>
            {networks.map(n => <option key={n.id} value={n.id}>{n.name ?? n.id}</option>)}
          </select>
        </div>

        {needsDevice && networkId && (
          <div>
            <label className="text-xs opacity-50 block mb-1">Step 2 — Pick a {KIND_META[kind as TemplateKind].label.toLowerCase()}</label>
            {devicesLoading ? (
              <p className="text-xs opacity-40 py-2">Loading devices…</p>
            ) : devices.length === 0 ? (
              <p className="text-xs text-amber-400/70 py-1">No {KIND_META[kind as TemplateKind].label.toLowerCase()} devices found in this network.</p>
            ) : (
              <div className="border border-white/10 rounded overflow-hidden max-h-36 overflow-y-auto">
                {devices.map(d => (
                  <button
                    key={d.serial}
                    onClick={() => setDeviceSerial(d.serial)}
                    className={[
                      'w-full flex items-center gap-2 px-3 py-2 text-xs text-left transition-colors',
                      deviceSerial === d.serial
                        ? 'bg-indigo-500/20 border-l-2 border-indigo-500'
                        : 'hover:bg-white/5 border-l-2 border-transparent',
                    ].join(' ')}
                  >
                    <span className="flex-1 font-medium">{d.name ?? d.serial}</span>
                    <span className="opacity-40 font-mono text-[10px]">{d.serial}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        <div>
          <label className="text-xs opacity-50 block mb-1">Template name</label>
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="e.g. Standard Core Switch"
            className="w-full bg-white/5 border border-white/10 rounded px-2 py-1.5 text-xs"
          />
        </div>

        <div className="flex gap-2 justify-end pt-1">
          <button onClick={onCancel} className="px-3 py-1.5 text-xs opacity-60 hover:opacity-100">Cancel</button>
          <button
            disabled={!canSave}
            onClick={() => onConfirm(
              name.trim(),
              networkId,
              kind || null,
              needsDevice ? deviceSerial : null,
              needsDevice ? (selectedDevice?.name ?? null) : null,
            )}
            className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed rounded text-xs"
          >
            Save Template
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Update `handlePromote` and `showPromote` call in `TemplatesView`**

In the `TemplatesView` function body, update `handlePromote`:

```typescript
const handlePromote = async (
  name: string,
  networkId: string,
  kind: TemplateKind | null,
  deviceSerial: string | null,
  deviceName: string | null,
) => {
  await promote(name, networkId, kind, deviceSerial, deviceName)
  setShowPromote(false)
}
```

Update the `PromoteModal` JSX call to pass `orgId`:

```tsx
{showPromote && (
  <PromoteModal
    orgId={orgId}
    tree={tree}
    onConfirm={handlePromote}
    onCancel={() => setShowPromote(false)}
  />
)}
```

- [ ] **Step 4: Update `TemplateCard` subtitle to show device name for device templates**

In `TemplatesView.tsx`, find the `TemplateCard` function and replace the subtitle line:

```tsx
// Replace this line:
<div className="text-xs opacity-40 mt-0.5 truncate">{tmpl.source_network_name ?? tmpl.source_network_id}</div>

// With:
<div className="text-xs opacity-40 mt-0.5 truncate">
  {tmpl.source_device_serial
    ? (tmpl.source_device_name ?? tmpl.source_device_serial)
    : (tmpl.source_network_name ?? tmpl.source_network_id)}
</div>
```

- [ ] **Step 5: Type-check**

```bash
cd "/Users/jkarnik/Code/Topology Maps/ui"
npx tsc --noEmit 2>&1 | grep -v "warn"
```

Expected: remaining errors only in `ScoresPanel` (not yet updated).

- [ ] **Step 6: Commit**

```bash
git add ui/src/components/ConfigBrowser/TemplatesView.tsx
git commit -m "feat: update PromoteModal with network+device picker for device templates"
```

---

### Task 11: TemplatesView.tsx — update ScoresPanel for device templates

**Files:**
- Modify: `ui/src/components/ConfigBrowser/TemplatesView.tsx`

- [ ] **Step 1: Replace the `ScoresPanel` component**

Replace the existing `ScoresPanel` function with two components — one for site templates (unchanged layout) and one for device templates (grouped by network):

```typescript
function DeviceScoreRow({ device }: { device: DeviceScore }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border border-white/10 rounded mb-1 overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-white/5 transition-colors"
      >
        <span className="text-xs opacity-80 w-32 text-left truncate">{device.name ?? device.serial}</span>
        <span className="text-[10px] opacity-40 font-mono w-24 text-left truncate">{device.serial}</span>
        <div className="flex-1"><ScoreBar pct={device.score_pct} /></div>
      </button>
      {open && (
        <div className="border-t border-white/10 p-2 space-y-1">
          {device.missing_areas.length > 0 && (
            <p className="text-xs text-red-400/70">Missing areas: {device.missing_areas.join(', ')}</p>
          )}
          {device.area_scores.map(as => (
            <div key={as.config_area} className="flex items-center gap-2">
              <span className="text-xs font-mono opacity-60 w-40 truncate">{as.config_area}</span>
              <div className="flex-1"><ScoreBar pct={as.score_pct} /></div>
              {as.change_count > 0 && (
                <span className="text-xs text-red-400/60">{as.change_count} change{as.change_count !== 1 ? 's' : ''}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function NetworkDeviceGroup({ group }: { group: NetworkDeviceScores }) {
  const [open, setOpen] = useState(false)
  const color = group.aggregate_score >= 90 ? 'text-green-400' : group.aggregate_score >= 60 ? 'text-amber-400' : 'text-red-400'
  return (
    <div className="border border-white/10 rounded mb-2 overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-white/5 transition-colors"
      >
        <span className="text-xs opacity-50">{open ? '▼' : '▶'}</span>
        <span className="text-xs font-medium flex-1 text-left truncate">{group.network_name}</span>
        <span className="text-xs opacity-40">{group.device_count} device{group.device_count !== 1 ? 's' : ''}</span>
        <span className={`text-xs font-semibold ml-2 ${color}`}>{group.aggregate_score}%</span>
      </button>
      {open && (
        <div className="border-t border-white/10 p-2">
          {group.devices.map(d => <DeviceScoreRow key={d.serial} device={d} />)}
        </div>
      )}
    </div>
  )
}

function ScoresPanel({ scoresData, kind }: { scoresData: TemplateScoresResponse | DeviceTemplateScoresResponse; kind: TemplateKind | null }) {
  if (isSiteScores(scoresData)) {
    const prefix = kind ? KIND_AREA_PREFIX[kind] : undefined
    const scores = prefix
      ? scoresData.scores.filter(s =>
          s.area_scores.some(a => a.config_area.startsWith(prefix) && !s.missing_areas.includes(a.config_area))
        )
      : scoresData.scores
    return (
      <div>
        <div className="flex items-center gap-2 mb-3">
          <p className="text-xs opacity-50">
            {scoresData.template.name} · {scores.length} network{scores.length !== 1 ? 's' : ''} · {scoresData.template.area_count} template areas
          </p>
          <KindBadge kind={kind} />
        </div>
        {scores.length === 0 ? (
          <p className="text-xs opacity-40 p-4 text-center">No networks collected yet — run a baseline first.</p>
        ) : (
          scores.map(score => <NetworkScoreRow key={score.network_id} score={score} />)
        )}
      </div>
    )
  }

  // Device template
  const { networks } = scoresData as DeviceTemplateScoresResponse
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <p className="text-xs opacity-50">
          {scoresData.template.name} · {networks.length} network{networks.length !== 1 ? 's' : ''} · {scoresData.template.area_count} template areas
        </p>
        <KindBadge kind={kind} />
      </div>
      {networks.length === 0 ? (
        <p className="text-xs opacity-40 p-4 text-center">No devices collected yet — run a baseline first.</p>
      ) : (
        networks.map(g => <NetworkDeviceGroup key={g.network_id} group={g} />)
      )}
    </div>
  )
}
```

- [ ] **Step 2: Type-check — expect clean**

```bash
cd "/Users/jkarnik/Code/Topology Maps/ui"
npx tsc --noEmit 2>&1 | grep -v "warn"
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add ui/src/components/ConfigBrowser/TemplatesView.tsx
git commit -m "feat: device template scoring panel grouped by network"
```

---

### Task 12: End-to-end smoke test

- [ ] **Step 1: Run full backend test suite**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
python3 -m pytest server/tests/ -v --tb=short 2>&1 | tail -30
```

Expected: all tests pass (no failures, no errors).

- [ ] **Step 2: Restart Docker and verify the UI loads**

```bash
docker compose down && docker compose up --build -d
```

Then open the app in a browser and confirm:
- Config Browser → Compare tab → Templates subtab loads without console errors
- Clicking "+ Promote a network" opens the modal with a "Template type" dropdown
- Selecting Switch/Gateway/AP shows the two-step flow (network → device)
- Selecting Site shows the original single-step network picker

- [ ] **Step 3: Final commit tag**

```bash
git log --oneline -8
```

Expected: clean commit history with one commit per task.
