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
