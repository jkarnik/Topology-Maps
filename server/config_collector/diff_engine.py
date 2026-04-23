from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Union
import hashlib, json


@dataclass
class FieldChanged:
    key: str
    before: object
    after: object

@dataclass
class FieldAdded:
    key: str
    value: object

@dataclass
class FieldRemoved:
    key: str
    value: object

@dataclass
class SecretChanged:
    key: str

@dataclass
class RowAdded:
    identity: object
    row: dict

@dataclass
class RowRemoved:
    identity: object
    row: dict

@dataclass
class RowChanged:
    identity: object
    field_changes: list

DiffChange = Union[FieldChanged, FieldAdded, FieldRemoved, SecretChanged, RowAdded, RowRemoved, RowChanged]


@dataclass
class DiffResult:
    shape: Literal["object", "array"]
    changes: list
    unchanged_count: int


def _stable_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()

def _is_secret_key(key: str) -> bool:
    return key.endswith("_hash")

def _object_diff(a: dict, b: dict, prefix: str = "") -> tuple[list, int]:
    changes: list = []
    unchanged = 0
    all_keys = set(a) | set(b)
    for k in sorted(all_keys):
        full_key = f"{prefix}.{k}" if prefix else k
        in_a, in_b = k in a, k in b
        if not in_a:
            changes.append(FieldAdded(key=full_key, value=b[k]))
        elif not in_b:
            changes.append(FieldRemoved(key=full_key, value=a[k]))
        elif isinstance(a[k], dict) and isinstance(b[k], dict):
            sub_changes, sub_unchanged = _object_diff(a[k], b[k], prefix=full_key)
            changes.extend(sub_changes)
            unchanged += sub_unchanged
        elif _is_secret_key(k):
            if a[k] != b[k]:
                changes.append(SecretChanged(key=full_key))
            else:
                unchanged += 1
        elif _stable_hash(a[k]) != _stable_hash(b[k]):
            changes.append(FieldChanged(key=full_key, before=a[k], after=b[k]))
        else:
            unchanged += 1
    return changes, unchanged

# Identity key registry — maps config_area name to the field used to match rows
_IDENTITY_KEYS: dict[str, str | None] = {
    "appliance_vlans": "id",
    "appliance_firewall_l3": None,   # None = position-based
    "wireless_ssids": "number",
    "switch_device_ports": "portId",
}

def _get_identity_key(area_name: str, sample_row: dict) -> str | None:
    if area_name in _IDENTITY_KEYS:
        return _IDENTITY_KEYS[area_name]
    # Fallback: first field ending in Id, id, or number
    for suffix in ("Id", "id", "number"):
        for k in sample_row:
            if k.endswith(suffix):
                return k
    return None  # position fallback

def _array_diff(area_name: str, rows_a: list[dict], rows_b: list[dict]) -> tuple[list, int]:
    changes: list = []
    unchanged = 0
    sample = (rows_a or rows_b or [{}])[0]
    id_key = _get_identity_key(area_name, sample)

    if id_key is None:
        # Position-based matching
        for i, (ra, rb) in enumerate(zip(rows_a, rows_b)):
            sub, sub_u = _object_diff(ra, rb)
            if sub:
                changes.append(RowChanged(identity=i, field_changes=sub))
            else:
                unchanged += 1
        for i in range(len(rows_b), len(rows_a)):
            changes.append(RowRemoved(identity=i, row=rows_a[i]))
        for i in range(len(rows_a), len(rows_b)):
            changes.append(RowAdded(identity=i, row=rows_b[i]))
        return changes, unchanged

    # Rows lacking id_key are silently excluded — matches Meraki clean-response assumption
    map_a = {r[id_key]: r for r in rows_a if id_key in r}
    map_b = {r[id_key]: r for r in rows_b if id_key in r}
    all_ids = list(map_a) + [k for k in map_b if k not in map_a]
    for identity in all_ids:
        if identity not in map_a:
            changes.append(RowAdded(identity=identity, row=map_b[identity]))
        elif identity not in map_b:
            changes.append(RowRemoved(identity=identity, row=map_a[identity]))
        else:
            sub, sub_u = _object_diff(map_a[identity], map_b[identity])
            if sub:
                changes.append(RowChanged(identity=identity, field_changes=sub))
            else:
                unchanged += 1
    return changes, unchanged

def compute_diff(blob_a: dict, blob_b: dict) -> DiffResult:
    # Detect shape: if any top-level value is a list, use array mode
    is_array = any(isinstance(v, list) for v in blob_a.values()) or \
               any(isinstance(v, list) for v in blob_b.values())
    if is_array:
        # area_name is the first list-valued key present in either blob
        _merged = {**blob_a, **blob_b}
        area_name = next((k for k in _merged if isinstance(_merged[k], list)), next(iter(blob_b or blob_a), ""))
        rows_a = blob_a.get(area_name, [])
        rows_b = blob_b.get(area_name, [])
        changes, unchanged = _array_diff(area_name, rows_a, rows_b)
        return DiffResult(shape="array", changes=changes, unchanged_count=unchanged)
    changes, unchanged = _object_diff(blob_a, blob_b)
    return DiffResult(shape="object", changes=changes, unchanged_count=unchanged)
