# Plan 1.05 — Meraki Pagination Helper

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.
>
> **Execution guideline (user directive):** Before executing ANY task, evaluate whether it can be split further into smaller, independently executable subtasks. Commit frequently.

**Goal:** Extend the existing `MerakiClient` with a `_get_paginated()` method that follows RFC 5988 `Link: <url>; rel="next"` headers and concatenates paginated list responses. Includes a `CONFIG_MAX_PAGES` safety ceiling that aborts rather than silently truncates. No new endpoint methods yet — just the helper that later endpoint plans will use.

**Architecture:** New method `_get_paginated(path, params=None, per_page=1000, max_pages=None)` on `MerakiClient`. Parses `Link` headers using stdlib `re`. Each page fetch passes through the existing `RateLimiter`. Returns a single flat list of concatenated items. Raises `MaxPagesExceeded` if the ceiling is hit, so the caller can surface the failure loudly.

**Tech Stack:** Python 3.9+, httpx (existing), pytest, pytest-asyncio, `respx` (httpx mocking) — add to requirements.txt.

**Spec reference:** [docs/superpowers/specs/2026-04-22-config-collection-phase1-design.md — Pagination handling](../specs/2026-04-22-config-collection-phase1-design.md#pagination-handling)

**Depends on:** None (extends existing `server/meraki_client.py`).

**Unblocks:** Plans 1.06, 1.07, 1.08, 1.09 (all Meraki endpoint methods that need pagination).

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `server/meraki_client.py` | Modify | Add `_get_paginated()` method, `MaxPagesExceeded` exception, `_parse_link_header()` helper |
| `server/tests/test_meraki_pagination.py` | Create | Unit tests with `respx`-mocked httpx responses |
| `server/requirements.txt` | Modify | Add `respx>=0.20` to dev deps |

---

## Task 1: Add respx dependency

- [ ] **Step 1.1: Add `respx` to requirements.txt**

Open `server/requirements.txt` and append:

```
respx>=0.20
```

- [ ] **Step 1.2: Install**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pip install respx`

Expected: `Successfully installed respx-...`

- [ ] **Step 1.3: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/requirements.txt
git commit -m "chore: add respx for httpx mocking in pagination tests (Plan 1.05)"
```

---

## Task 2: Parse RFC 5988 Link header

- [ ] **Step 2.1: Write failing test**

Create `server/tests/test_meraki_pagination.py`:

```python
"""Tests for MerakiClient pagination (Plan 1.05)."""
from __future__ import annotations

import pytest
import respx
import httpx

from server.meraki_client import MerakiClient, _parse_link_header, MaxPagesExceeded


def test_parse_link_header_with_next():
    header = '<https://api.meraki.com/api/v1/foo?startingAfter=abc>; rel="next"'
    assert _parse_link_header(header) == "https://api.meraki.com/api/v1/foo?startingAfter=abc"


def test_parse_link_header_multiple_rels():
    header = (
        '<https://api.meraki.com/api/v1/foo?startingAfter=abc>; rel="next", '
        '<https://api.meraki.com/api/v1/foo>; rel="first", '
        '<https://api.meraki.com/api/v1/foo?startingAfter=xyz>; rel="last"'
    )
    assert _parse_link_header(header) == "https://api.meraki.com/api/v1/foo?startingAfter=abc"


def test_parse_link_header_no_next_returns_none():
    header = '<https://api.meraki.com/api/v1/foo>; rel="first"'
    assert _parse_link_header(header) is None


def test_parse_link_header_empty_or_none():
    assert _parse_link_header(None) is None
    assert _parse_link_header("") is None
```

- [ ] **Step 2.2: Run to verify it fails**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_meraki_pagination.py::test_parse_link_header_with_next -v`

Expected: `ImportError: cannot import name '_parse_link_header'`.

- [ ] **Step 2.3: Implement `_parse_link_header` and `MaxPagesExceeded`**

In `server/meraki_client.py`, add near the top (after imports):

```python
import re as _re


class MaxPagesExceeded(Exception):
    """Raised when paginated fetch exceeds the configured page ceiling."""


_LINK_NEXT_RE = _re.compile(r'<([^>]+)>;\s*rel="next"')


def _parse_link_header(header: str | None) -> str | None:
    """Return the URL of the rel=next link, or None if absent."""
    if not header:
        return None
    m = _LINK_NEXT_RE.search(header)
    return m.group(1) if m else None
```

- [ ] **Step 2.4: Run tests — should pass**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_meraki_pagination.py -v`

Expected: 4 passing tests.

- [ ] **Step 2.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/meraki_client.py server/tests/test_meraki_pagination.py
git commit -m "feat(meraki): parse RFC 5988 Link headers for pagination (Plan 1.05)"
```

---

## Task 3: `_get_paginated()` — single page (no pagination)

- [ ] **Step 3.1: Write failing test**

Append to `server/tests/test_meraki_pagination.py`:

```python
import os


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MERAKI_API_KEY", "test-key")
    c = MerakiClient(api_key="test-key")
    yield c


@pytest.mark.asyncio
async def test_get_paginated_single_page_no_link(client):
    """A response without a Link header returns just the body."""
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/123/admins").mock(
            return_value=httpx.Response(200, json=[{"id": "1"}, {"id": "2"}])
        )
        result = await client._get_paginated("/organizations/123/admins")
    assert result == [{"id": "1"}, {"id": "2"}]
```

- [ ] **Step 3.2: Run — should fail**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_meraki_pagination.py::test_get_paginated_single_page_no_link -v`

Expected: `AttributeError: 'MerakiClient' object has no attribute '_get_paginated'`.

- [ ] **Step 3.3: Implement minimal `_get_paginated`**

Add to `MerakiClient` in `server/meraki_client.py`:

```python
    async def _get_paginated(
        self,
        path: str,
        params: Optional[dict] = None,
        per_page: int = 1000,
        max_pages: int = 100,
    ) -> list:
        """Fetch `path` with RFC 5988 Link-header pagination, concatenating items.

        Each page fetch passes through the rate limiter. Raises
        `MaxPagesExceeded` if more than `max_pages` pages would be fetched.
        """
        merged_params = {"perPage": per_page, **(params or {})}
        await self._limiter.acquire()
        resp = await self._client.get(path, params=merged_params)
        resp.raise_for_status()
        results = list(resp.json())

        page_count = 1
        next_url = _parse_link_header(resp.headers.get("Link"))
        while next_url:
            if page_count >= max_pages:
                raise MaxPagesExceeded(f"exceeded max_pages={max_pages} for {path}")
            await self._limiter.acquire()
            resp = await self._client.get(next_url)
            resp.raise_for_status()
            results.extend(resp.json())
            page_count += 1
            next_url = _parse_link_header(resp.headers.get("Link"))

        return results
```

- [ ] **Step 3.4: Run — should pass**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_meraki_pagination.py -v`

Expected: 5 tests pass.

- [ ] **Step 3.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/meraki_client.py server/tests/test_meraki_pagination.py
git commit -m "feat(meraki): _get_paginated with single-page path (Plan 1.05)"
```

---

## Task 4: Multi-page concatenation

- [ ] **Step 4.1: Write failing test**

Append to `server/tests/test_meraki_pagination.py`:

```python
@pytest.mark.asyncio
async def test_get_paginated_follows_link_next(client):
    """Multiple pages are concatenated in order."""
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        page1 = httpx.Response(
            200,
            json=[{"id": "1"}, {"id": "2"}],
            headers={"Link": '<https://api.meraki.com/api/v1/organizations/123/inventory/devices?startingAfter=2>; rel="next"'},
        )
        page2 = httpx.Response(
            200,
            json=[{"id": "3"}, {"id": "4"}],
            headers={"Link": '<https://api.meraki.com/api/v1/organizations/123/inventory/devices?startingAfter=4>; rel="next"'},
        )
        page3 = httpx.Response(200, json=[{"id": "5"}])  # no Link header → terminal
        mock.get("/organizations/123/inventory/devices").mock(return_value=page1)
        mock.get(url__startswith="https://api.meraki.com/api/v1/organizations/123/inventory/devices?startingAfter=2").mock(return_value=page2)
        mock.get(url__startswith="https://api.meraki.com/api/v1/organizations/123/inventory/devices?startingAfter=4").mock(return_value=page3)

        result = await client._get_paginated("/organizations/123/inventory/devices")
    assert result == [{"id": "1"}, {"id": "2"}, {"id": "3"}, {"id": "4"}, {"id": "5"}]
```

- [ ] **Step 4.2: Run — should pass (implementation already handles this)**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_meraki_pagination.py::test_get_paginated_follows_link_next -v`

Expected: `PASSED`.

- [ ] **Step 4.3: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/tests/test_meraki_pagination.py
git commit -m "test(meraki): multi-page pagination concatenation (Plan 1.05)"
```

---

## Task 5: `MaxPagesExceeded` safety ceiling

- [ ] **Step 5.1: Write failing test**

Append to `server/tests/test_meraki_pagination.py`:

```python
@pytest.mark.asyncio
async def test_get_paginated_raises_on_max_pages(client):
    """If more pages than max_pages exist, raise MaxPagesExceeded."""
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        always_has_next = httpx.Response(
            200,
            json=[{"id": "x"}],
            headers={"Link": '<https://api.meraki.com/api/v1/foo?startingAfter=x>; rel="next"'},
        )
        mock.get("/foo").mock(return_value=always_has_next)
        mock.get(url__startswith="https://api.meraki.com/api/v1/foo?startingAfter=").mock(return_value=always_has_next)

        with pytest.raises(MaxPagesExceeded):
            await client._get_paginated("/foo", max_pages=3)
```

- [ ] **Step 5.2: Run — should pass (implementation already raises)**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_meraki_pagination.py::test_get_paginated_raises_on_max_pages -v`

Expected: `PASSED`.

- [ ] **Step 5.3: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/tests/test_meraki_pagination.py
git commit -m "test(meraki): MaxPagesExceeded safety ceiling (Plan 1.05)"
```

---

## Completion Checklist

- [ ] `_get_paginated`, `MaxPagesExceeded`, `_parse_link_header` exist in `server/meraki_client.py`
- [ ] `pytest server/tests/test_meraki_pagination.py -v` shows 7 passing tests
- [ ] Full test suite still green
- [ ] 5 commits on branch

## What This Unblocks

- Plans 1.06–1.09: each adds Meraki endpoint methods, using `_get_paginated` where the catalog says `paginated=True`.

## Out of Scope

- Retry / backoff on transient failures — handled in Plan 1.12 (targeted puller).
- Integration test against real Meraki API — contract tests use recorded fixtures in later plans.
