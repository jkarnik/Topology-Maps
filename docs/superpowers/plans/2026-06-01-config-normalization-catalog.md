# Config Normalization Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strip per-device identity fields (IPs, serials, BLE UUIDs, etc.) from config observations at collection time so golden templates and compliance scoring never show false-positive drift.

**Architecture:** A new `NORMALIZATION_PATHS` dict in `redaction_catalog.py` lists fields to delete per config area (parallel to the existing `REDACTION_PATHS` for secrets). A new `delete_path()` walker in `redactor.py` removes those fields in place. `redact()` calls `delete_path` after masking secrets, so normalization is transparent to callers — scanner.py needs no changes. `create_template` in `store.py` adds a one-line exclusion to skip `device_metadata` areas when building template snapshots.

**Tech Stack:** Python, SQLite, pytest

---

## File Map

| File | Change |
|---|---|
| `server/config_collector/redaction_catalog.py` | Add `NORMALIZATION_PATHS` dict |
| `server/config_collector/redactor.py` | Add `delete_path()`; wire into `redact()` |
| `server/config_collector/store.py` | Filter `device_metadata` in `create_template` |
| `server/tests/test_redactor.py` | Tests for `delete_path` + normalization in `redact()` |
| `server/tests/test_redaction_catalog.py` | Smoke test for `NORMALIZATION_PATHS` catalog shape |
| `server/tests/test_config_store_templates.py` | Test that `device_metadata` is excluded from template areas |

---

### Task 1: Add NORMALIZATION_PATHS to redaction_catalog.py

**Files:**
- Modify: `server/config_collector/redaction_catalog.py`
- Test: `server/tests/test_redaction_catalog.py`

- [ ] **Step 1: Write a failing catalog shape test**

Add to the end of `server/tests/test_redaction_catalog.py`:

```python
from server.config_collector.redaction_catalog import NORMALIZATION_PATHS


def test_normalization_paths_is_dict_of_lists():
    assert isinstance(NORMALIZATION_PATHS, dict)
    for area, paths in NORMALIZATION_PATHS.items():
        assert isinstance(area, str), f"{area!r} key is not a str"
        assert isinstance(paths, list), f"{area!r} value is not a list"
        for p in paths:
            assert isinstance(p, str), f"path {p!r} in {area!r} is not a str"


def test_normalization_paths_covers_expected_areas():
    expected = {
        "device_management_interface",
        "switch_device_ports",
        "switch_device_warm_spare",
        "switch_device_routing_interfaces",
        "switch_device_routing_static_routes",
        "wireless_device_bluetooth",
    }
    assert expected == set(NORMALIZATION_PATHS.keys())
```

- [ ] **Step 2: Run to verify failure**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
python3 -m pytest server/tests/test_redaction_catalog.py::test_normalization_paths_is_dict_of_lists -v
```

Expected: `ImportError: cannot import name 'NORMALIZATION_PATHS'`

- [ ] **Step 3: Add NORMALIZATION_PATHS to redaction_catalog.py**

Append to the end of `server/config_collector/redaction_catalog.py`:

```python

NORMALIZATION_PATHS: dict[str, list[str]] = {
    # Per-device identity fields in management interface
    "device_management_interface": [
        "ddnsHostname",
        "wan1.staticIp",
        "wan1.staticGateway",
        "wan2.staticIp",
        "wan2.staticGateway",
    ],
    # Read-only hardware capability list — not a setting
    "switch_device_ports": [
        "[*].linkNegotiationCapabilities",
    ],
    # Serial of the paired HA device — unique per install
    "switch_device_warm_spare": [
        "spareSerial",
    ],
    # Per-device/site IP addresses and internal Meraki IDs
    "switch_device_routing_interfaces": [
        "[*].interfaceId",
        "[*].ip",
        "[*].subnet",
        "[*].defaultGateway",
    ],
    # Site-specific routing details and internal IDs
    "switch_device_routing_static_routes": [
        "[*].staticRouteId",
        "[*].nextHopIp",
        "[*].subnet",
    ],
    # Per-AP BLE beacon identifiers
    "wireless_device_bluetooth": [
        "uuid",
        "major",
        "minor",
    ],
}
```

- [ ] **Step 4: Run catalog tests**

```bash
python3 -m pytest server/tests/test_redaction_catalog.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add server/config_collector/redaction_catalog.py server/tests/test_redaction_catalog.py
git commit -m "feat: add NORMALIZATION_PATHS catalog for per-device noise fields"
```

---

### Task 2: Add delete_path() to redactor.py

**Files:**
- Modify: `server/config_collector/redactor.py`
- Test: `server/tests/test_redactor.py`

- [ ] **Step 1: Write failing tests for delete_path**

Add to the end of `server/tests/test_redactor.py`:

```python
from server.config_collector.redactor import delete_path


def test_delete_top_level_key():
    payload = {"serial": "Q2KD-0001", "enabled": True}
    delete_path(payload, [("key", "serial")])
    assert "serial" not in payload
    assert payload["enabled"] is True


def test_delete_nested_key():
    payload = {"wan1": {"staticIp": "1.2.3.4", "vlan": 10}}
    delete_path(payload, [("key", "wan1"), ("key", "staticIp")])
    assert "staticIp" not in payload["wan1"]
    assert payload["wan1"]["vlan"] == 10


def test_delete_array_wildcard_field():
    payload = [{"id": "1", "caps": ["auto"]}, {"id": "2", "caps": ["100M"]}]
    delete_path(payload, [("array",), ("key", "caps")])
    assert "caps" not in payload[0]
    assert "caps" not in payload[1]
    assert payload[0]["id"] == "1"


def test_delete_missing_path_is_silent():
    payload = {"enabled": True}
    delete_path(payload, [("key", "doesNotExist")])  # must not raise
    assert payload == {"enabled": True}


def test_delete_array_step_on_non_array_is_silent():
    payload = {"ports": "not-a-list"}
    delete_path(payload, [("array",), ("key", "id")])  # must not raise
    assert payload == {"ports": "not-a-list"}
```

- [ ] **Step 2: Run to verify failure**

```bash
python3 -m pytest server/tests/test_redactor.py::test_delete_top_level_key -v
```

Expected: `ImportError: cannot import name 'delete_path'`

- [ ] **Step 3: Implement delete_path in redactor.py**

Add the following after the `mask_path` function (before the `SENTINEL_KEY` line is fine, but after `mask_path`'s closing brace):

```python
def delete_path(payload: Any, steps: list[tuple]) -> None:
    """Mutate `payload` in place, deleting the field at `steps`.

    Missing keys and type mismatches are silently skipped — same
    leniency as mask_path.
    """
    if not steps:
        return
    head, *rest = steps

    if head[0] == "key":
        key = head[1]
        if not isinstance(payload, dict) or key not in payload:
            return
        if not rest:
            del payload[key]
        else:
            delete_path(payload[key], rest)

    elif head[0] == "array":
        if not isinstance(payload, list):
            return
        for item in payload:
            delete_path(item, rest)
```

- [ ] **Step 4: Run delete_path tests**

```bash
python3 -m pytest server/tests/test_redactor.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add server/config_collector/redactor.py server/tests/test_redactor.py
git commit -m "feat: add delete_path walker to redactor"
```

---

### Task 3: Wire normalization into redact()

**Files:**
- Modify: `server/config_collector/redactor.py`
- Test: `server/tests/test_redactor.py`

- [ ] **Step 1: Write failing end-to-end normalization test**

Add to the end of `server/tests/test_redactor.py`:

```python
def test_redact_strips_normalization_fields():
    """redact() must delete per-device noise fields for known areas."""
    payload = [
        {"portId": "1", "vlan": 10, "linkNegotiationCapabilities": ["Auto negotiate", "100M"]},
        {"portId": "2", "vlan": 20, "linkNegotiationCapabilities": ["Auto negotiate"]},
    ]
    canonical, hash_hex, byte_size, hot = redact(payload, "switch_device_ports")
    import json
    result = json.loads(canonical)
    assert "linkNegotiationCapabilities" not in result[0]
    assert "linkNegotiationCapabilities" not in result[1]
    assert result[0]["vlan"] == 10
    assert result[1]["portId"] == "2"


def test_redact_strips_bluetooth_identifiers():
    payload = {"uuid": "abc-123", "major": 1, "minor": 5, "advertisingEnabled": True, "scanningEnabled": False}
    canonical, _, _, _ = redact(payload, "wireless_device_bluetooth")
    import json
    result = json.loads(canonical)
    assert "uuid" not in result
    assert "major" not in result
    assert "minor" not in result
    assert result["advertisingEnabled"] is True
    assert result["scanningEnabled"] is False


def test_redact_unknown_area_no_normalization():
    """Areas not in NORMALIZATION_PATHS are left untouched."""
    payload = {"serial": "Q2KD-0001", "firmware": "18.107.2"}
    canonical, _, _, _ = redact(payload, "device_metadata")
    import json
    result = json.loads(canonical)
    assert result["serial"] == "Q2KD-0001"
```

- [ ] **Step 2: Run to verify failure**

```bash
python3 -m pytest server/tests/test_redactor.py::test_redact_strips_normalization_fields -v
```

Expected: FAIL — `linkNegotiationCapabilities` still present in result.

- [ ] **Step 3: Update redact() to apply normalization**

In `server/config_collector/redactor.py`, update the import at the top of the file (the line that imports `REDACTION_PATHS`):

```python
from server.config_collector.redaction_catalog import REDACTION_PATHS, NORMALIZATION_PATHS
```

Then in the `redact()` function body, add the normalization loop immediately after the existing redaction loop:

```python
    # Existing redaction loop (already present — do not duplicate):
    for path in REDACTION_PATHS.get(config_area, ()):
        mask_path(working, parse_path(path))

    # New: delete per-device noise fields
    for path in NORMALIZATION_PATHS.get(config_area, ()):
        delete_path(working, parse_path(path))
```

The full updated `redact()` body should look like:

```python
def redact(payload: Any, config_area: str) -> tuple[str, str, int, dict]:
    working = copy.deepcopy(payload)

    for path in REDACTION_PATHS.get(config_area, ()):
        mask_path(working, parse_path(path))

    for path in NORMALIZATION_PATHS.get(config_area, ()):
        delete_path(working, parse_path(path))

    canonical = _canonical_dumps(working)
    encoded = canonical.encode("utf-8")
    return canonical, _hashlib.sha256(encoded).hexdigest(), len(encoded), _extract_hot_columns(payload)
```

- [ ] **Step 4: Run all redactor tests**

```bash
python3 -m pytest server/tests/test_redactor.py server/tests/test_redactor_guard.py -v
```

Expected: all pass.

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
python3 -m pytest server/tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add server/config_collector/redactor.py
git commit -m "feat: apply normalization paths inside redact() to strip per-device noise fields"
```

---

### Task 4: Exclude device_metadata from create_template

**Files:**
- Modify: `server/config_collector/store.py`
- Test: `server/tests/test_config_store_templates.py`

- [ ] **Step 1: Write a failing test**

Add to the end of `server/tests/test_config_store_templates.py`:

```python
def test_create_device_template_excludes_device_metadata(conn):
    """device_metadata must never appear in template areas."""
    h_ports = _seed_blob(conn, '{"portId": "1", "vlan": 10}')
    h_meta = _seed_blob(conn, '{"serial": "Q2SW-0001", "name": "Core-SW"}')

    _seed_device_observation(conn, "org1", "Q2SW-0001", "switch_device_ports", h_ports)
    _seed_device_observation(conn, "org1", "Q2SW-0001", "device_metadata", h_meta)

    tmpl = store.create_template(
        conn,
        org_id="org1",
        name="No Metadata Template",
        network_id="net1",
        network_name=None,
        kind="switch",
        device_serial="Q2SW-0001",
        device_name="Core-SW",
    )

    area_names = [a["config_area"] for a in tmpl["areas"]]
    assert "device_metadata" not in area_names
    assert "switch_device_ports" in area_names
```

- [ ] **Step 2: Run to verify failure**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
python3 -m pytest server/tests/test_config_store_templates.py::test_create_device_template_excludes_device_metadata -v
```

Expected: FAIL — `assert "device_metadata" not in area_names` fails.

- [ ] **Step 3: Add exclusion constant and filter in store.py**

In `server/config_collector/store.py`, add the constant near the top of the file (after the imports, before the first function):

```python
_TEMPLATE_EXCLUDED_AREAS: frozenset[str] = frozenset({"device_metadata"})
```

Then in the `create_template` function, update the `for row in rows:` loop (around line 413) to skip excluded areas:

```python
    areas = []
    for row in rows:
        if row["config_area"] in _TEMPLATE_EXCLUDED_AREAS:
            continue
        conn.execute(
            """INSERT INTO config_template_areas (template_id, config_area, sub_key, blob_hash)
               VALUES (?, ?, ?, ?)""",
            (template_id, row["config_area"], row["sub_key"], row["hash"]),
        )
        areas.append({"config_area": row["config_area"], "sub_key": row["sub_key"], "blob_hash": row["hash"]})
```

- [ ] **Step 4: Run all template store tests**

```bash
python3 -m pytest server/tests/test_config_store_templates.py -v
```

Expected: all pass.

- [ ] **Step 5: Run full test suite**

```bash
python3 -m pytest server/tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add server/config_collector/store.py server/tests/test_config_store_templates.py
git commit -m "feat: exclude device_metadata from golden template areas"
```
