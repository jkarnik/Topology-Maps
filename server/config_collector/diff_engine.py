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

def compute_diff(blob_a: dict, blob_b: dict) -> DiffResult:
    is_array = any(isinstance(v, list) for v in blob_a.values()) or \
               any(isinstance(v, list) for v in blob_b.values())
    if is_array:
        raise NotImplementedError("Array mode implemented in Task 2")
    changes, unchanged = _object_diff(blob_a, blob_b)
    return DiffResult(shape="object", changes=changes, unchanged_count=unchanged)
