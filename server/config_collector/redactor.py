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

from server.config_collector.canonical_json import dumps as _canonical_dumps
import hashlib as _hashlib

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


# Path masking ----------------------------------------------------------------

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
