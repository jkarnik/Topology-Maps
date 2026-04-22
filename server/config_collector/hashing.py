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
