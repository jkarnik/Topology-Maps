# Plan 1.02 — Hashing Primitives

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Execution guideline (user directive):** Before executing ANY task below, evaluate whether that task can be split further into smaller, independently executable subtasks. Prefer doing less per turn over doing more. Commit frequently.

**Goal:** Provide two small, pure-function utility modules — canonical JSON serialization and SHA-256 hashing — that the redactor and storage layers will consume. Deterministic in, deterministic out. No I/O. No external dependencies beyond stdlib.

**Architecture:** One module `canonical_json.py` with a `dumps()` function that produces byte-identical output for semantically identical inputs (sorted keys, compact separators, UTF-8, no trailing whitespace). One module `hashing.py` with a `sha256_canonical()` function that hashes a payload via its canonical form. Both pure-Python, stdlib only.

**Tech Stack:** Python 3.9+, `json` (stdlib), `hashlib` (stdlib), pytest.

**Spec reference:** [docs/superpowers/specs/2026-04-22-config-collection-phase1-design.md — Secret Redaction → Redaction flow (step 3)](../specs/2026-04-22-config-collection-phase1-design.md#redaction-flow)

**Depends on:** None. Can run in parallel with Plan 1.01.

**Unblocks:** Plan 1.03 (redactor), Plan 1.10 (storage blobs + observations).

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `server/config_collector/__init__.py` | Create | Package init (empty module marker) |
| `server/config_collector/canonical_json.py` | Create | `dumps(obj) -> str` — deterministic JSON serialization |
| `server/config_collector/hashing.py` | Create | `sha256_canonical(obj) -> str` — hex digest of canonical form |
| `server/tests/test_canonical_json.py` | Create | Unit tests for canonical_json |
| `server/tests/test_hashing.py` | Create | Unit tests for hashing |

Rationale: Keeping canonical JSON and hashing separate (rather than one combined module) makes each testable in isolation and avoids the hashing module pulling JSON dependencies for unrelated callers.

---

## Task 1: Create the package init

**Files:**
- Create: `server/config_collector/__init__.py`

- [ ] **Step 1.1: Create the package directory and init file**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
mkdir -p server/config_collector
```

Create `server/config_collector/__init__.py`:

```python
"""Config collection subsystem for Phase 1 of the Meraki config management initiative.

See docs/superpowers/specs/2026-04-22-config-collection-phase1-design.md
"""
```

- [ ] **Step 1.2: Verify Python can import the package**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && python -c "from server import config_collector; print(config_collector.__doc__[:50])"`

Expected: `Config collection subsystem for Phase 1 of the Mer`

- [ ] **Step 1.3: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/__init__.py
git commit -m "feat(config): create config_collector package (Plan 1.02)"
```

---

## Task 2: Canonical JSON — flat types

Flat types (null, bool, int, float, string) must serialize identically across Python versions and platforms.

**Files:**
- Create: `server/config_collector/canonical_json.py`
- Create: `server/tests/test_canonical_json.py`

- [ ] **Step 2.1: Write the failing test**

Create `server/tests/test_canonical_json.py`:

```python
"""Tests for canonical JSON serialization (Plan 1.02)."""
from __future__ import annotations

import pytest

from server.config_collector.canonical_json import dumps


def test_flat_types_serialize_deterministically():
    assert dumps(None) == "null"
    assert dumps(True) == "true"
    assert dumps(False) == "false"
    assert dumps(0) == "0"
    assert dumps(42) == "42"
    assert dumps(-17) == "-17"
    assert dumps("hello") == '"hello"'
    assert dumps("") == '""'


def test_unicode_preserved_not_escaped():
    """Non-ASCII characters are kept as UTF-8, not \\u-escaped."""
    assert dumps("café") == '"café"'
    assert dumps("日本語") == '"日本語"'
```

- [ ] **Step 2.2: Run the test to verify it fails**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_canonical_json.py -v`

Expected: `FAILED` — `ModuleNotFoundError: No module named 'server.config_collector.canonical_json'`.

- [ ] **Step 2.3: Write the minimal implementation**

Create `server/config_collector/canonical_json.py`:

```python
"""Deterministic JSON serialization for content-addressed hashing.

Produces byte-identical output for semantically identical inputs:
  - Object keys sorted alphabetically
  - No extra whitespace (compact separators)
  - UTF-8 preserved (non-ASCII chars NOT \\u-escaped)
  - No trailing newline

This output is suitable for SHA-256 hashing: identical payloads
produce identical hashes regardless of insertion order or source
formatting.
"""
from __future__ import annotations

import json
from typing import Any


def dumps(obj: Any) -> str:
    """Serialize `obj` as a canonical JSON string."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
```

- [ ] **Step 2.4: Run the test to verify it passes**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_canonical_json.py -v`

Expected: `PASSED` (2 tests).

- [ ] **Step 2.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/canonical_json.py server/tests/test_canonical_json.py
git commit -m "feat(config): canonical JSON serialization for flat types (Plan 1.02)"
```

---

## Task 3: Canonical JSON — nested structures & key sorting

Object keys must sort alphabetically; arrays preserve order; nested structures recurse.

**Files:**
- Test: `server/tests/test_canonical_json.py`

- [ ] **Step 3.1: Write the failing test**

Append to `server/tests/test_canonical_json.py`:

```python
def test_object_keys_sort_alphabetically():
    """Same object, different insertion order → same canonical output."""
    a = {"b": 1, "a": 2, "c": 3}
    b = {"c": 3, "a": 2, "b": 1}
    assert dumps(a) == dumps(b)
    assert dumps(a) == '{"a":2,"b":1,"c":3}'


def test_array_order_preserved():
    """Arrays are order-sensitive; reversing changes the output."""
    assert dumps([1, 2, 3]) == "[1,2,3]"
    assert dumps([3, 2, 1]) == "[3,2,1]"
    assert dumps([1, 2, 3]) != dumps([3, 2, 1])


def test_nested_objects_recurse():
    nested = {"outer": {"z": 1, "a": 2}, "arr": [{"y": 1, "x": 2}]}
    assert dumps(nested) == '{"arr":[{"x":2,"y":1}],"outer":{"a":2,"z":1}}'


def test_no_whitespace_or_trailing_newline():
    assert dumps({"a": 1, "b": [1, 2]}) == '{"a":1,"b":[1,2]}'
    assert not dumps({"a": 1}).endswith("\n")
```

- [ ] **Step 3.2: Run the tests to verify they pass**

Because `json.dumps(..., sort_keys=True, separators=(',',':'))` already handles all of this, no code change is needed — the canonical_json implementation from Task 2 already satisfies these properties.

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_canonical_json.py -v`

Expected: All 6 tests pass.

If any test fails, the implementation is missing `sort_keys=True` or the correct `separators` tuple. Re-read `server/config_collector/canonical_json.py` and fix.

- [ ] **Step 3.3: Commit the expanded test coverage**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/tests/test_canonical_json.py
git commit -m "test(config): verify canonical JSON nested-structure determinism (Plan 1.02)"
```

---

## Task 4: SHA-256 hashing of canonical form

Hash utility that produces a hex digest from the canonical JSON of any payload.

**Files:**
- Create: `server/config_collector/hashing.py`
- Create: `server/tests/test_hashing.py`

- [ ] **Step 4.1: Write the failing test**

Create `server/tests/test_hashing.py`:

```python
"""Tests for content hashing (Plan 1.02)."""
from __future__ import annotations

from server.config_collector.hashing import sha256_canonical


def test_sha256_returns_hex_string():
    """Result is a 64-char lowercase hex string."""
    h = sha256_canonical({"a": 1})
    assert isinstance(h, str)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_sha256_deterministic_for_same_payload():
    """Same semantic payload in different key order → same hash."""
    a = {"z": 1, "a": 2, "nested": {"y": 1, "x": 2}}
    b = {"a": 2, "z": 1, "nested": {"x": 2, "y": 1}}
    assert sha256_canonical(a) == sha256_canonical(b)


def test_sha256_different_for_different_payloads():
    assert sha256_canonical({"a": 1}) != sha256_canonical({"a": 2})
    assert sha256_canonical([1, 2, 3]) != sha256_canonical([1, 2, 4])
    # Order-sensitive for arrays
    assert sha256_canonical([1, 2, 3]) != sha256_canonical([3, 2, 1])


def test_sha256_empty_object_is_stable():
    # Known SHA-256 of '{}' (canonical form of empty dict)
    assert sha256_canonical({}) == "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
```

- [ ] **Step 4.2: Run the tests to verify they fail**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_hashing.py -v`

Expected: `FAILED` — `ModuleNotFoundError: No module named 'server.config_collector.hashing'`.

- [ ] **Step 4.3: Write the minimal implementation**

Create `server/config_collector/hashing.py`:

```python
"""SHA-256 hashing of canonical JSON for content-addressed storage."""
from __future__ import annotations

import hashlib
from typing import Any

from server.config_collector.canonical_json import dumps


def sha256_canonical(obj: Any) -> str:
    """Return the SHA-256 hex digest of `obj` in canonical JSON form.

    Two semantically identical payloads (same keys, same values, regardless
    of insertion order) produce the same digest. Used as the primary key of
    the `config_blobs` storage table.
    """
    payload = dumps(obj).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
```

- [ ] **Step 4.4: Run the tests to verify they pass**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_hashing.py -v`

Expected: All 4 tests pass.

- [ ] **Step 4.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/hashing.py server/tests/test_hashing.py
git commit -m "feat(config): SHA-256 canonical hashing utility (Plan 1.02)"
```

---

## Task 5: Byte-size helper for storage

Storage needs the payload byte length for `config_blobs.byte_size`. Since this is always computed alongside a hash, co-locate in the same module.

**Files:**
- Modify: `server/config_collector/hashing.py`
- Modify: `server/tests/test_hashing.py`

- [ ] **Step 5.1: Write the failing test**

Append to `server/tests/test_hashing.py`:

```python
from server.config_collector.hashing import canonical_payload


def test_canonical_payload_returns_hash_payload_and_size():
    payload, hash_hex, byte_size = canonical_payload({"a": 1, "b": [1, 2]})
    assert payload == '{"a":1,"b":[1,2]}'
    assert len(hash_hex) == 64
    assert byte_size == len(payload.encode("utf-8"))


def test_canonical_payload_unicode_byte_size():
    """Byte size reflects UTF-8 encoding, not char count."""
    payload, _, byte_size = canonical_payload({"name": "café"})
    # 'café' is 4 characters but 5 bytes in UTF-8 (é = 2 bytes)
    assert byte_size == len(payload.encode("utf-8"))
    assert byte_size > len(payload)  # because of multi-byte char
```

- [ ] **Step 5.2: Run the tests to verify they fail**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_hashing.py -v`

Expected: `ImportError: cannot import name 'canonical_payload'`.

- [ ] **Step 5.3: Add the helper**

Append to `server/config_collector/hashing.py`:

```python
def canonical_payload(obj: Any) -> tuple[str, str, int]:
    """Return `(canonical_str, sha256_hex, byte_size)` for `obj`.

    Computed together so callers that need all three (e.g. the storage
    layer writing a blob row) don't pay for redundant serialization.
    """
    payload = dumps(obj)
    encoded = payload.encode("utf-8")
    return payload, hashlib.sha256(encoded).hexdigest(), len(encoded)
```

- [ ] **Step 5.4: Run the tests to verify they pass**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_hashing.py -v`

Expected: All 6 tests pass.

- [ ] **Step 5.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/hashing.py server/tests/test_hashing.py
git commit -m "feat(config): canonical_payload helper returning hash+bytes together (Plan 1.02)"
```

---

## Completion Checklist

- [ ] `server/config_collector/__init__.py`, `canonical_json.py`, `hashing.py` all exist
- [ ] `pytest server/tests/test_canonical_json.py server/tests/test_hashing.py -v` shows 12 passing tests
- [ ] Full test suite still passes: `pytest server/tests/ -v`
- [ ] 5 commits on the branch, one per task

## What This Plan Unblocks

- Plan 1.03 (redactor) uses `canonical_json.dumps()` and `hashing.sha256_canonical()` to mask secrets and compute blob hashes.
- Plan 1.10 (storage: blobs + observations) uses `canonical_payload()` to populate `config_blobs` rows.

## Out of Scope

- Redaction logic — Plan 1.03.
- Schema inserts using the hash — Plan 1.10.
- Streaming-hash for large payloads — not needed at Meraki response sizes (all individual responses comfortably fit in memory).

