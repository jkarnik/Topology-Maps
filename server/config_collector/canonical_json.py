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
