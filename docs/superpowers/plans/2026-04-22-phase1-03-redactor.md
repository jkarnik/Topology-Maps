# Plan 1.03 — Redactor

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Execution guideline (user directive):** Before executing ANY task below, evaluate whether that task can be split further into smaller, independently executable subtasks. Prefer doing less per turn over doing more. Commit frequently.

**Goal:** Walk Meraki config payloads, mask all known secret fields with `{"_redacted": true, "_hash": "<sha256-of-original>"}` sentinels, and produce a canonical, redacted payload + its SHA-256 hash suitable for insertion into `config_blobs`. Includes a regex-guard test that fails the build on any secret-looking value escaping redaction.

**Architecture:** Two modules. `redaction_catalog.py` defines the initial map of `config_area → list of JSON paths to redact` (data only). `redactor.py` implements the walker: given a raw response and a `config_area` key, it produces `(redacted_payload_str, blob_hash_hex, byte_size, hot_columns)`. The walker is lenient — missing paths are silently skipped (responses vary in structure across Meraki versions). A separate regex-guard test uses field-name and value-shape heuristics to catch new secret-bearing fields as Meraki evolves.

**Tech Stack:** Python 3.9+, stdlib `re`, pytest. Consumes `server.config_collector.canonical_json` and `server.config_collector.hashing`.

**Spec reference:** [docs/superpowers/specs/2026-04-22-config-collection-phase1-design.md — Secret Redaction](../specs/2026-04-22-config-collection-phase1-design.md#secret-redaction)

**Depends on:** Plan 1.02 (hashing primitives).

**Unblocks:** Plan 1.12 (targeted puller — calls the redactor on every response).

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `server/config_collector/redaction_catalog.py` | Create | Static map `REDACTION_PATHS: dict[str, list[str]]` — `config_area → JSON paths to redact` |
| `server/config_collector/redactor.py` | Create | `redact(payload, config_area) -> (str, str, int, dict)` — mask + canonicalize + hash + extract hot columns |
| `server/tests/test_redaction_catalog.py` | Create | Sanity tests: catalog keys are valid `config_area` strings; paths are non-empty |
| `server/tests/test_redactor.py` | Create | Redaction walker behavior: masking, sentinel shape, hash determinism, hot-column extraction |
| `server/tests/test_redactor_guard.py` | Create | Regex-guard fail-safe: scans a corpus of recorded Meraki fixtures for unredacted secret-looking values |
| `server/tests/fixtures/meraki/` | Create | Initial fixture directory for recorded Meraki responses (seeded with a minimal sample; real fixtures recorded by operator later) |

---

## Task 1: Create the redaction catalog (data only)

Start with just the data structure — no walker logic yet. Isolates "what is a secret" from "how we mask."

**Files:**
- Create: `server/config_collector/redaction_catalog.py`
- Create: `server/tests/test_redaction_catalog.py`

- [ ] **Step 1.1: Write the failing test**

Create `server/tests/test_redaction_catalog.py`:

```python
"""Tests for the redaction catalog (Plan 1.03)."""
from __future__ import annotations

from server.config_collector.redaction_catalog import REDACTION_PATHS


def test_catalog_is_a_dict():
    assert isinstance(REDACTION_PATHS, dict)


def test_catalog_has_expected_core_areas():
    """The spec mandates these config_area keys carry secrets."""
    expected = {
        "wireless_ssids",
        "wireless_ssid_identity_psks",
        "appliance_site_to_site_vpn",
        "network_snmp",
        "org_snmp",
        "network_webhooks_http_servers",
    }
    missing = expected - REDACTION_PATHS.keys()
    assert not missing, f"Catalog missing entries: {missing}"


def test_catalog_values_are_non_empty_path_lists():
    for area, paths in REDACTION_PATHS.items():
        assert isinstance(paths, list), f"{area}: paths must be a list"
        assert len(paths) > 0, f"{area}: must have at least one path"
        for p in paths:
            assert isinstance(p, str) and p, f"{area}: path must be a non-empty string"
```

- [ ] **Step 1.2: Run the test to verify it fails**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_redaction_catalog.py -v`

Expected: `FAILED` — `ModuleNotFoundError`.

- [ ] **Step 1.3: Create the catalog**

Create `server/config_collector/redaction_catalog.py`:

```python
"""Map of config_area → JSON paths that must be redacted before storage.

Path syntax is a simple dot-and-bracket notation:
  - `foo.bar` — nested key access
  - `foo[*].bar` — for every item in the `foo` array, access `.bar`
  - `foo.bar[*]` — `foo.bar` is an array whose items are themselves replaced

The walker in `redactor.py` interprets these paths leniently: if a path
does not resolve against a particular response (e.g. field absent,
array empty), it is silently skipped.

This catalog is THE authoritative list of known secret fields.
Reviewed quarterly; updated whenever Meraki adds or renames endpoints.
"""
from __future__ import annotations

REDACTION_PATHS: dict[str, list[str]] = {
    # Per-SSID PSKs and RADIUS secrets (on the list endpoint)
    "wireless_ssids": [
        "[*].psk",
        "[*].radiusServers[*].secret",
        "[*].radiusAccountingServers[*].secret",
    ],
    # Identity PSK passphrases (per-SSID sub-endpoint)
    "wireless_ssid_identity_psks": [
        "[*].passphrase",
    ],
    # Site-to-site VPN pre-shared keys
    "appliance_site_to_site_vpn": [
        "peers[*].secret",
        "peers[*].ikev2.secret",
    ],
    # Network-level SNMP community/user passphrases
    "network_snmp": [
        "communityString",
        "users[*].passphrase",
    ],
    # Org-level SNMP
    "org_snmp": [
        "v2CommunityString",
        "users[*].passphrase",
    ],
    # Webhook HTTP server shared secrets
    "network_webhooks_http_servers": [
        "[*].sharedSecret",
    ],
}
```

- [ ] **Step 1.4: Run the test to verify it passes**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_redaction_catalog.py -v`

Expected: All 3 tests pass.

- [ ] **Step 1.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/redaction_catalog.py server/tests/test_redaction_catalog.py
git commit -m "feat(config): initial redaction catalog with known Meraki secret paths (Plan 1.03)"
```

---

## Task 2: Path parser

Parse the `foo.bar[*].baz` mini-language into a list of step tuples the walker can consume.

**Files:**
- Create: `server/config_collector/redactor.py` (start here)
- Create: `server/tests/test_redactor.py`

- [ ] **Step 2.1: Write the failing test**

Create `server/tests/test_redactor.py`:

```python
"""Tests for the redactor walker (Plan 1.03)."""
from __future__ import annotations

import pytest

from server.config_collector.redactor import parse_path


def test_parse_simple_key():
    assert parse_path("foo") == [("key", "foo")]


def test_parse_nested_key():
    assert parse_path("foo.bar.baz") == [("key", "foo"), ("key", "bar"), ("key", "baz")]


def test_parse_array_wildcard():
    assert parse_path("foo[*].bar") == [("key", "foo"), ("array",), ("key", "bar")]


def test_parse_top_level_array():
    assert parse_path("[*].psk") == [("array",), ("key", "psk")]


def test_parse_array_of_arrays():
    assert parse_path("peers[*].secrets[*]") == [
        ("key", "peers"), ("array",), ("key", "secrets"), ("array",),
    ]


def test_parse_rejects_malformed():
    with pytest.raises(ValueError):
        parse_path("")
    with pytest.raises(ValueError):
        parse_path("foo[bar]")  # only [*] is supported
```

- [ ] **Step 2.2: Run the tests to verify they fail**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_redactor.py -v`

Expected: `FAILED` — `ModuleNotFoundError`.

- [ ] **Step 2.3: Create the redactor module with `parse_path`**

Create `server/config_collector/redactor.py`:

```python
"""Secret-field redaction walker for Meraki config responses.

Given a raw parsed-JSON payload and a `config_area` key, produces a
redacted canonical JSON string + its SHA-256 hash. Secret fields are
replaced in-place with {"_redacted": true, "_hash": "<sha256>"}
sentinel objects so change-detection still works without exposing
plaintext.
"""
from __future__ import annotations

import re
from typing import Any

# Path parser ----------------------------------------------------------------

_TOKEN = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)|\[\*\]|\.")


def parse_path(path: str) -> list[tuple]:
    """Parse a redaction path into walk steps.

    Supported syntax:
      foo            → [("key", "foo")]
      foo.bar        → [("key", "foo"), ("key", "bar")]
      foo[*].bar     → [("key", "foo"), ("array",), ("key", "bar")]
      [*].psk        → [("array",), ("key", "psk")]

    Raises ValueError on empty or malformed paths.
    """
    if not path:
        raise ValueError("empty path")

    steps: list[tuple] = []
    i = 0
    while i < len(path):
        ch = path[i]
        if ch == ".":
            i += 1
            continue
        if ch == "[":
            if path[i : i + 3] != "[*]":
                raise ValueError(f"malformed path fragment at {i}: {path!r}")
            steps.append(("array",))
            i += 3
            continue
        # Read an identifier
        m = re.match(r"[A-Za-z_][A-Za-z0-9_]*", path[i:])
        if not m:
            raise ValueError(f"unexpected character at {i}: {path!r}")
        steps.append(("key", m.group(0)))
        i += m.end()

    if not steps:
        raise ValueError(f"no steps parsed from {path!r}")
    return steps
```

- [ ] **Step 2.4: Run the tests to verify they pass**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_redactor.py -v`

Expected: All 6 tests pass.

- [ ] **Step 2.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/redactor.py server/tests/test_redactor.py
git commit -m "feat(config): redactor path parser with array-wildcard support (Plan 1.03)"
```

---

## Task 3: Mask a single path

Given a parsed path and a payload, replace the target value(s) with the sentinel. Lenient on missing paths.

**Files:**
- Modify: `server/config_collector/redactor.py`
- Modify: `server/tests/test_redactor.py`

- [ ] **Step 3.1: Write the failing test**

Append to `server/tests/test_redactor.py`:

```python
from server.config_collector.redactor import mask_path


def test_mask_top_level_key():
    payload = {"psk": "supersecret", "name": "Guest"}
    mask_path(payload, [("key", "psk")])
    assert payload["psk"] == {"_redacted": True, "_hash": _sha256("supersecret")}
    assert payload["name"] == "Guest"  # untouched


def test_mask_array_wildcard():
    payload = [{"psk": "a"}, {"psk": "b"}, {"psk": "c"}]
    mask_path(payload, [("array",), ("key", "psk")])
    assert payload[0]["psk"]["_redacted"] is True
    assert payload[1]["psk"]["_redacted"] is True
    assert payload[2]["psk"]["_redacted"] is True
    assert payload[0]["psk"]["_hash"] == _sha256("a")


def test_mask_missing_path_is_silent():
    """Paths that don't resolve are skipped, not raised."""
    payload = {"name": "Guest"}  # no psk
    mask_path(payload, [("key", "psk")])
    assert payload == {"name": "Guest"}


def test_mask_handles_null_value():
    """A null value at the target becomes a redacted sentinel of null."""
    payload = {"psk": None}
    mask_path(payload, [("key", "psk")])
    # null is hashed as the string "null"
    assert payload["psk"] == {"_redacted": True, "_hash": _sha256(None)}


# helper
def _sha256(value):
    import hashlib
    import json
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

- [ ] **Step 3.2: Run the tests to verify they fail**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_redactor.py -v`

Expected: `ImportError: cannot import name 'mask_path'`.

- [ ] **Step 3.3: Implement `mask_path`**

Append to `server/config_collector/redactor.py`:

```python
from server.config_collector.canonical_json import dumps as _canonical_dumps
import hashlib as _hashlib

SENTINEL_KEY = "_redacted"
HASH_KEY = "_hash"


def _hash_value(value: Any) -> str:
    """Hash a single value by its canonical JSON form."""
    return _hashlib.sha256(_canonical_dumps(value).encode("utf-8")).hexdigest()


def _make_sentinel(value: Any) -> dict:
    return {SENTINEL_KEY: True, HASH_KEY: _hash_value(value)}


def mask_path(payload: Any, steps: list[tuple]) -> None:
    """Mutate `payload` in place, replacing values at `steps` with sentinels.

    Missing keys or non-array types where an array step is expected are
    silently skipped — Meraki response shapes vary, and strict mode
    would fight that.
    """
    if not steps:
        return
    head, *rest = steps

    if head[0] == "key":
        key = head[1]
        if not isinstance(payload, dict) or key not in payload:
            return
        if not rest:
            payload[key] = _make_sentinel(payload[key])
        else:
            mask_path(payload[key], rest)

    elif head[0] == "array":
        if not isinstance(payload, list):
            return
        if not rest:
            # Replace each array element itself
            for i in range(len(payload)):
                payload[i] = _make_sentinel(payload[i])
        else:
            for item in payload:
                mask_path(item, rest)
```

- [ ] **Step 3.4: Run the tests to verify they pass**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_redactor.py -v`

Expected: All 10 tests pass.

- [ ] **Step 3.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/redactor.py server/tests/test_redactor.py
git commit -m "feat(config): single-path redaction walker with lenient missing-path handling (Plan 1.03)"
```

---

## Task 4: Top-level `redact()` entry point

The public API: given a raw payload and a config_area, produce `(redacted_canonical_str, hash_hex, byte_size, hot_columns)`.

**Files:**
- Modify: `server/config_collector/redactor.py`
- Modify: `server/tests/test_redactor.py`

- [ ] **Step 4.1: Write the failing test**

Append to `server/tests/test_redactor.py`:

```python
from server.config_collector.redactor import redact


def test_redact_wireless_ssids_masks_psks():
    payload = [
        {"number": 0, "name": "Corp", "enabled": True, "psk": "corppass123", "authMode": "psk"},
        {"number": 1, "name": "Guest", "enabled": True, "psk": "guestpass", "authMode": "psk"},
    ]
    redacted_str, hash_hex, byte_size, hot = redact(payload, "wireless_ssids")

    # Canonical string is valid JSON
    import json
    parsed = json.loads(redacted_str)
    assert parsed[0]["psk"] == {"_redacted": True, "_hash": _sha256("corppass123")}
    assert parsed[1]["psk"] == {"_redacted": True, "_hash": _sha256("guestpass")}
    assert parsed[0]["name"] == "Corp"  # name retained

    assert len(hash_hex) == 64
    assert byte_size == len(redacted_str.encode("utf-8"))


def test_redact_unknown_config_area_passes_through():
    """An area not in the catalog → no redaction, but still canonicalized + hashed."""
    payload = {"foo": 1}
    redacted_str, hash_hex, byte_size, hot = redact(payload, "unknown_area")
    assert redacted_str == '{"foo":1}'


def test_redact_same_payload_different_key_order_same_hash():
    a = {"b": 1, "a": 2, "c": [3, 2, 1]}
    b = {"c": [3, 2, 1], "a": 2, "b": 1}
    _, h1, _, _ = redact(a, "unknown_area")
    _, h2, _, _ = redact(b, "unknown_area")
    assert h1 == h2


def test_redact_different_secret_different_hash():
    """Hashing on the sentinel distinguishes changed secrets."""
    _, h1, _, _ = redact([{"psk": "v1"}], "wireless_ssids")
    _, h2, _, _ = redact([{"psk": "v2"}], "wireless_ssids")
    assert h1 != h2


def test_redact_extracts_name_and_enabled_hot_columns():
    payload = {"name": "Store 42", "enabled": True, "other": 123}
    _, _, _, hot = redact(payload, "unknown_area")
    assert hot == {"name_hint": "Store 42", "enabled_hint": 1}


def test_redact_hot_columns_none_when_absent():
    payload = {"other": 123}
    _, _, _, hot = redact(payload, "unknown_area")
    assert hot == {"name_hint": None, "enabled_hint": None}
```

- [ ] **Step 4.2: Run the tests to verify they fail**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_redactor.py -v`

Expected: `ImportError: cannot import name 'redact'`.

- [ ] **Step 4.3: Implement `redact()`**

Append to `server/config_collector/redactor.py`:

```python
import copy
from server.config_collector.redaction_catalog import REDACTION_PATHS


def _extract_hot_columns(payload: Any) -> dict:
    """Pull denormalized hot columns used by config_observations."""
    name_hint = None
    enabled_hint = None
    if isinstance(payload, dict):
        name = payload.get("name")
        if isinstance(name, str):
            name_hint = name
        enabled = payload.get("enabled")
        if isinstance(enabled, bool):
            enabled_hint = 1 if enabled else 0
    return {"name_hint": name_hint, "enabled_hint": enabled_hint}


def redact(payload: Any, config_area: str) -> tuple[str, str, int, dict]:
    """Mask secrets in `payload` and return canonical form + hash + size + hot columns.

    Returns
    -------
    (redacted_canonical_str, sha256_hex, byte_size, hot_columns)
      - redacted_canonical_str : JSON string with secrets replaced by
        {"_redacted": true, "_hash": "..."} sentinels
      - sha256_hex : SHA-256 of the canonical string (UTF-8 encoded)
      - byte_size  : UTF-8 byte count of the canonical string
      - hot_columns : {"name_hint": str|None, "enabled_hint": 0|1|None}
    """
    # Deep-copy so the caller's input is never mutated
    working = copy.deepcopy(payload)

    for path in REDACTION_PATHS.get(config_area, ()):
        mask_path(working, parse_path(path))

    canonical = _canonical_dumps(working)
    encoded = canonical.encode("utf-8")
    return canonical, _hashlib.sha256(encoded).hexdigest(), len(encoded), _extract_hot_columns(payload)
```

- [ ] **Step 4.4: Run the tests to verify they pass**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_redactor.py -v`

Expected: All 16 tests pass.

- [ ] **Step 4.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/redactor.py server/tests/test_redactor.py
git commit -m "feat(config): redact() top-level entry point with hot-column extraction (Plan 1.03)"
```

---

## Task 5: Seed a minimal fixtures directory

The regex-guard test in Task 6 needs recorded Meraki responses to scan. Start with a few hand-crafted minimal examples; an operator will run a real recorder script in a later plan.

**Files:**
- Create: `server/tests/fixtures/__init__.py` (empty marker)
- Create: `server/tests/fixtures/meraki/__init__.py` (empty marker)
- Create: `server/tests/fixtures/meraki/wireless_ssids_sample.json`
- Create: `server/tests/fixtures/meraki/appliance_site_to_site_vpn_sample.json`
- Create: `server/tests/fixtures/meraki/network_snmp_sample.json`

- [ ] **Step 5.1: Create empty `__init__.py` markers**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
mkdir -p server/tests/fixtures/meraki
touch server/tests/fixtures/__init__.py
touch server/tests/fixtures/meraki/__init__.py
```

- [ ] **Step 5.2: Create the fixture files**

Create `server/tests/fixtures/meraki/wireless_ssids_sample.json`:

```json
[
  {
    "number": 0,
    "name": "Corp",
    "enabled": true,
    "authMode": "psk",
    "encryptionMode": "wpa",
    "psk": "corporatesecret123",
    "radiusServers": [
      {"host": "10.0.0.5", "port": 1812, "secret": "radius-shared-secret"}
    ]
  },
  {
    "number": 1,
    "name": "Guest",
    "enabled": true,
    "authMode": "open"
  },
  {
    "number": 2,
    "name": "Unconfigured SSID 3",
    "enabled": false
  }
]
```

Create `server/tests/fixtures/meraki/appliance_site_to_site_vpn_sample.json`:

```json
{
  "mode": "spoke",
  "hubs": [{"hubId": "N_123", "useDefaultRoute": false}],
  "subnets": [{"localSubnet": "192.168.1.0/24", "useVpn": true}],
  "peers": [
    {"name": "HQ", "publicIp": "203.0.113.10", "privateSubnets": ["10.0.0.0/8"], "secret": "psk-to-hq"},
    {"name": "DC2", "publicIp": "203.0.113.20", "privateSubnets": ["10.1.0.0/16"], "secret": "psk-to-dc2"}
  ]
}
```

Create `server/tests/fixtures/meraki/network_snmp_sample.json`:

```json
{
  "access": "community",
  "communityString": "meraki-community-secret",
  "users": [
    {"username": "operator", "passphrase": "user-snmp-pass"}
  ]
}
```

- [ ] **Step 5.3: Sanity test — fixtures load as valid JSON**

Append to `server/tests/test_redactor.py`:

```python
import json
from pathlib import Path


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "meraki"


def test_all_fixtures_parse_as_valid_json():
    files = list(FIXTURES_DIR.glob("*.json"))
    assert len(files) >= 3, "expected at least 3 seed fixtures"
    for f in files:
        data = json.loads(f.read_text())
        assert data is not None
```

- [ ] **Step 5.4: Run the test**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_redactor.py::test_all_fixtures_parse_as_valid_json -v`

Expected: `PASSED`.

- [ ] **Step 5.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/tests/fixtures/__init__.py server/tests/fixtures/meraki/ server/tests/test_redactor.py
git commit -m "test(config): seed minimal Meraki response fixtures for redactor tests (Plan 1.03)"
```

---

## Task 6: Regex-guard test (field-name heuristics)

Fails the build if any secret-suggesting field name survives redaction with a non-null, non-sentinel value.

**Files:**
- Create: `server/tests/test_redactor_guard.py`

- [ ] **Step 6.1: Write the test (targeted to fail if redaction misses fields)**

Create `server/tests/test_redactor_guard.py`:

```python
"""Regex-guard tests: fail the build if any secret-looking field escapes redaction.

Scans every recorded Meraki response fixture, runs it through the redactor
for its corresponding config_area, and walks the redacted payload for any
key whose name suggests a secret but whose value is not a sentinel.

This is the fail-safe that keeps the redaction catalog current as Meraki
evolves its API.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from server.config_collector.redactor import redact, SENTINEL_KEY

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "meraki"

# Maps fixture filename → config_area used in the redaction catalog
FIXTURE_AREA_MAP = {
    "wireless_ssids_sample.json": "wireless_ssids",
    "appliance_site_to_site_vpn_sample.json": "appliance_site_to_site_vpn",
    "network_snmp_sample.json": "network_snmp",
}

SECRET_KEY_PATTERN = re.compile(
    r"(?i)(psk|passphrase|password|secret|shared[-_]?key|community[-_]?string|token|api[-_]?key)"
)


def _walk(node, path=""):
    """Yield (path, key, value) for every key-value pair in nested structures."""
    if isinstance(node, dict):
        # If node itself is a redacted sentinel, skip — it is by definition masked
        if node.get(SENTINEL_KEY) is True:
            return
        for k, v in node.items():
            yield (path, k, v)
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _walk(item, f"{path}[{i}]")


@pytest.mark.parametrize("fixture_name,config_area", sorted(FIXTURE_AREA_MAP.items()))
def test_no_secret_field_escapes_redaction(fixture_name, config_area):
    """No field matching SECRET_KEY_PATTERN may have a non-null, non-sentinel value."""
    raw = json.loads((FIXTURES_DIR / fixture_name).read_text())
    redacted_str, _, _, _ = redact(raw, config_area)
    redacted = json.loads(redacted_str)

    violations: list[str] = []
    for parent_path, key, value in _walk(redacted):
        if not SECRET_KEY_PATTERN.search(key):
            continue
        if value is None or value == "":
            continue
        if isinstance(value, dict) and value.get(SENTINEL_KEY) is True:
            continue
        violations.append(f"{parent_path}.{key} = {value!r}")

    assert not violations, (
        f"Secret-looking fields escaped redaction in {fixture_name} "
        f"(config_area={config_area}):\n  " + "\n  ".join(violations) +
        "\n\nFix: add the missing path to REDACTION_PATHS in server/config_collector/redaction_catalog.py"
    )
```

- [ ] **Step 6.2: Run the test**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_redactor_guard.py -v`

Expected: All 3 parametrized tests pass. If any fail, the catalog is missing a path for that area — add it to `REDACTION_PATHS` and re-run.

- [ ] **Step 6.3: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/tests/test_redactor_guard.py
git commit -m "test(config): regex-guard fail-safe for secret-field redaction (Plan 1.03)"
```

---

## Task 7: Deliberately break-then-fix the regex guard

Prove the guard actually catches missing redactions. This task adds a fixture with a new secret-bearing field, confirms the guard fails, then updates the catalog to pass.

**Files:**
- Create: `server/tests/fixtures/meraki/webhook_http_servers_sample.json`
- Modify: `server/config_collector/redaction_catalog.py` (add a catalog entry AFTER proving the guard fails)
- Modify: `server/tests/test_redactor_guard.py` (register the new fixture)

- [ ] **Step 7.1: Add a new fixture with a `sharedSecret` field**

Create `server/tests/fixtures/meraki/webhook_http_servers_sample.json`:

```json
[
  {
    "id": "abc123",
    "name": "Splunk",
    "url": "https://splunk.internal/webhook",
    "sharedSecret": "splunk-webhook-secret"
  }
]
```

- [ ] **Step 7.2: Register the fixture WITHOUT adding its catalog entry**

In `server/tests/test_redactor_guard.py`, append to `FIXTURE_AREA_MAP`:

```python
    "webhook_http_servers_sample.json": "network_webhooks_http_servers",
```

- [ ] **Step 7.3: Run the guard — it should PASS**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_redactor_guard.py -v`

Expected: **PASS** — because the `network_webhooks_http_servers` area already has `[*].sharedSecret` in the catalog from Task 1. The guard correctly does nothing here because the masking is already in place.

**If it fails:** That means the catalog entry is missing — go back to `server/config_collector/redaction_catalog.py` and confirm the `network_webhooks_http_servers` entry has `"[*].sharedSecret"`.

- [ ] **Step 7.4: Deliberately remove the catalog entry to prove the guard catches it**

Temporarily comment out the `"[*].sharedSecret"` line in `server/config_collector/redaction_catalog.py`:

```python
    "network_webhooks_http_servers": [
        # "[*].sharedSecret",   # TEMPORARILY REMOVED for guard verification
    ],
```

- [ ] **Step 7.5: Run the guard — it should FAIL now**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_redactor_guard.py -v`

Expected: **FAIL** on `test_no_secret_field_escapes_redaction[webhook_http_servers_sample.json-network_webhooks_http_servers]` with message containing `[0].sharedSecret = 'splunk-webhook-secret'`.

This proves the regex-guard is wired correctly.

- [ ] **Step 7.6: Restore the catalog entry (uncomment)**

Revert the temporary comment in `server/config_collector/redaction_catalog.py`:

```python
    "network_webhooks_http_servers": [
        "[*].sharedSecret",
    ],
```

Also: the list must have no trailing comment-only line.

- [ ] **Step 7.7: Run the guard — passes again**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_redactor_guard.py -v`

Expected: All 4 parametrized tests pass.

- [ ] **Step 7.8: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/tests/fixtures/meraki/webhook_http_servers_sample.json server/tests/test_redactor_guard.py
git commit -m "test(config): expand regex-guard coverage to webhook shared secrets (Plan 1.03)"
```

---

## Completion Checklist

- [ ] `server/config_collector/redaction_catalog.py` and `redactor.py` exist
- [ ] `pytest server/tests/test_redaction_catalog.py server/tests/test_redactor.py server/tests/test_redactor_guard.py -v` shows all tests passing (23+ total)
- [ ] Full test suite still green: `pytest server/tests/ -v`
- [ ] 7 commits on the branch, one per task

## What This Plan Unblocks

- Plan 1.12 (targeted puller) — pipes each Meraki response through `redact()` before handing to storage.
- Plan 1.14 (change-log poller) — redacts old_value/new_value in change events before insert.

## Out of Scope

- Recording real Meraki fixtures (an operator runs a recorder script in a later utility plan).
- Admin PII handling — spec says retain unredacted; will be added in Plan 1.14 when we also consider the change_events.raw_json case.
- Value-shape regex heuristics (40-char hex API keys, printable-PSK lengths). Current field-name heuristic is sufficient for the Phase 1 cut; value-shape can be layered on later if a leak is ever discovered.



