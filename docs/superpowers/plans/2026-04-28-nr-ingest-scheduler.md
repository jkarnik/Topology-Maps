# NR Ingest Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated Docker service that pushes Meraki device entities to New Relic every 5 minutes, keeping them alive without manual intervention.

**Architecture:** A new `nr_ingest` service in docker-compose.yml mounts the existing `topology-data` volume to read `app.db` directly, then calls `push_all_devices.main()` in a loop. Credentials come from environment variables only — no `.env` file parsing inside the container.

**Tech Stack:** Python 3.11, Docker, httpx (already in requirements.txt)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `nr_ingest/scheduler.py` | Create | Entry point: validate env, loop push every 5 min |
| `nr_ingest/Dockerfile` | Create | Build image with nr_ingest + server code |
| `docker-compose.yml` | Modify | Add nr_ingest service with shared volume + env vars |

---

### Task 1: scheduler.py — env validation and push loop

**Files:**
- Create: `nr_ingest/scheduler.py`
- Create: `nr_ingest/tests/test_scheduler.py`

- [ ] **Step 1: Write the failing tests**

Create `nr_ingest/tests/test_scheduler.py`:

```python
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import scheduler


def test_validate_env_missing_both(monkeypatch):
    monkeypatch.delenv("NR_LICENSE_KEY", raising=False)
    monkeypatch.delenv("NR_ACCOUNT_ID", raising=False)
    with pytest.raises(SystemExit) as exc:
        scheduler._validate_env()
    assert exc.value.code == 1


def test_validate_env_missing_one(monkeypatch):
    monkeypatch.setenv("NR_LICENSE_KEY", "test-key")
    monkeypatch.delenv("NR_ACCOUNT_ID", raising=False)
    with pytest.raises(SystemExit) as exc:
        scheduler._validate_env()
    assert exc.value.code == 1


def test_validate_env_ok(monkeypatch):
    monkeypatch.setenv("NR_LICENSE_KEY", "test-key")
    monkeypatch.setenv("NR_ACCOUNT_ID", "12345")
    scheduler._validate_env()  # must not raise or exit


def test_run_once_success(monkeypatch):
    mock_module = MagicMock()
    mock_module.main.return_value = 0
    monkeypatch.setitem(sys.modules, "push_all_devices", mock_module)
    rc = scheduler.run_once()
    assert rc == 0
    mock_module.main.assert_called_once()


def test_run_once_failure(monkeypatch):
    mock_module = MagicMock()
    mock_module.main.return_value = 1
    monkeypatch.setitem(sys.modules, "push_all_devices", mock_module)
    rc = scheduler.run_once()
    assert rc == 1
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
cd /Users/jkarnik/Code/Topology\ Maps
python -m pytest nr_ingest/tests/test_scheduler.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'scheduler'`

- [ ] **Step 3: Create nr_ingest/scheduler.py**

```python
import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

PUSH_INTERVAL = 300  # seconds


def _validate_env() -> None:
    missing = [v for v in ("NR_LICENSE_KEY", "NR_ACCOUNT_ID") if not os.environ.get(v)]
    if missing:
        log.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)


def run_once() -> int:
    import push_all_devices
    return push_all_devices.main()


def main() -> None:
    _validate_env()
    log.info("NR ingest scheduler starting — push interval %ds", PUSH_INTERVAL)
    while True:
        log.info("Starting device push...")
        try:
            rc = run_once()
            if rc == 0:
                log.info("Push complete.")
            else:
                log.error("Push failed (exit code %d) — retrying in %ds", rc, PUSH_INTERVAL)
        except Exception as exc:
            log.error("Push raised exception: %s — retrying in %ds", exc, PUSH_INTERVAL)
        log.info("Sleeping %ds until next push...", PUSH_INTERVAL)
        time.sleep(PUSH_INTERVAL)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
cd /Users/jkarnik/Code/Topology\ Maps
python -m pytest nr_ingest/tests/test_scheduler.py -v
```

Expected output:
```
test_scheduler.py::test_validate_env_missing_both PASSED
test_scheduler.py::test_validate_env_missing_one PASSED
test_scheduler.py::test_validate_env_ok PASSED
test_scheduler.py::test_run_once_success PASSED
test_scheduler.py::test_run_once_failure PASSED
5 passed
```

- [ ] **Step 5: Commit**

```bash
git add nr_ingest/scheduler.py nr_ingest/tests/test_scheduler.py
git commit -m "feat(nr-ingest): add scheduler — push devices every 5 min"
```

---

### Task 2: Dockerfile

**Files:**
- Create: `nr_ingest/Dockerfile`

No unit tests for the Dockerfile — verified by building the image.

- [ ] **Step 1: Create nr_ingest/Dockerfile**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY nr_ingest/requirements.txt /app/nr_ingest/requirements.txt
RUN pip install --no-cache-dir -r /app/nr_ingest/requirements.txt
COPY nr_ingest/ /app/nr_ingest/
COPY server/ /app/server/
CMD ["python", "/app/nr_ingest/scheduler.py"]
```

- [ ] **Step 2: Build the image to verify it compiles**

```bash
cd /Users/jkarnik/Code/Topology\ Maps
docker build -f nr_ingest/Dockerfile -t nr-ingest-test .
```

Expected: `Successfully built <image-id>` with no errors.

- [ ] **Step 3: Commit**

```bash
git add nr_ingest/Dockerfile
git commit -m "feat(nr-ingest): add Dockerfile for scheduler service"
```

---

### Task 3: docker-compose.yml — add nr_ingest service

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add the nr_ingest service**

Open `docker-compose.yml` and add the following service block after the `ui` service, before the `networks:` key:

```yaml
  nr_ingest:
    build:
      context: .
      dockerfile: nr_ingest/Dockerfile
    depends_on:
      server:
        condition: service_healthy
    environment:
      - NR_LICENSE_KEY=${NR_LICENSE_KEY}
      - NR_ACCOUNT_ID=${NR_ACCOUNT_ID}
    volumes:
      - topology-data:/app/data
    networks:
      - topology-net
```

- [ ] **Step 2: Validate the compose file**

```bash
cd /Users/jkarnik/Code/Topology\ Maps
docker compose config --quiet && echo "Config valid"
```

Expected: `Config valid` with no errors.

- [ ] **Step 3: Verify the service starts and pushes on first run**

Ensure `NR_LICENSE_KEY` and `NR_ACCOUNT_ID` are in your local `.env`, then:

```bash
docker compose up --build nr_ingest
```

Watch the logs. Expected output within the first 30 seconds:
```
nr_ingest-1  | NR ingest scheduler starting — push interval 300s
nr_ingest-1  | Starting device push...
nr_ingest-1  | Device counts:
nr_ingest-1  |   access_point: ...
nr_ingest-1  | Push complete.
nr_ingest-1  | Sleeping 300s until next push...
```

If you see `Missing required environment variables`, the env vars are not set in `.env`.

If you see `SQLite topology cache is empty`, run a topology refresh in the UI first to populate `app.db`.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(nr-ingest): add nr_ingest scheduler service to docker-compose"
```
