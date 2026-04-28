# NR Ingest Scheduler — Design Spec

**Date:** 2026-04-28
**Goal:** Keep Meraki device entities alive in New Relic by pushing topology events every 5 minutes from a dedicated Docker service.

---

## Background

New Relic entity tags with the `tags.` prefix expire after 4 hours without a new event, and entities are tombstoned after ~8 days of silence. Running `push_all_devices.py` manually is insufficient to prevent this on a live Lightsail deployment. A scheduled push running inside Docker solves this without any manual intervention.

---

## Architecture

A new `nr_ingest` Docker service is added to `docker-compose.yml` alongside `simulator`, `server`, and `ui`. It shares the existing `topology-data` named volume, which the server mounts at `/app/data`. The `nr_ingest` container mounts the same volume at the same path, so `data_source.py`'s local fallback (`/app/data/app.db`) resolves correctly — no `docker cp` needed.

```
topology-data volume
     │
     ├── server         (writes app.db on topology refresh)
     └── nr_ingest      (reads app.db → pushes to NR Events API every 5 min)
```

The service starts after the server passes its healthcheck (`depends_on: server: condition: service_healthy`), ensuring the DB is populated before the first push.

`server/db.py` is imported transitively by `data_source.py`, so the image copies both `nr_ingest/` and `server/` into `/app/`.

---

## Credentials

`scheduler.py` reads `NR_LICENSE_KEY` and `NR_ACCOUNT_ID` purely from `os.environ` — no `.env` file parsing. The container runtime is responsible for injecting these.

- **Locally:** docker-compose reads `NR_LICENSE_KEY` and `NR_ACCOUNT_ID` from the `.env` file at the project root (the same file already used for `MERAKI_API_KEY`) and passes them into the container via `environment:` in `docker-compose.yml`.
- **Lightsail:** env vars are set as deployment secrets in the Lightsail container service console. No file access required.

The inline `.env` loader in `push_all_devices.py` becomes a no-op inside the container because `os.environ` is already populated before it runs.

---

## Components

### `nr_ingest/Dockerfile` (new)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY nr_ingest/requirements.txt /app/nr_ingest/requirements.txt
RUN pip install --no-cache-dir -r /app/nr_ingest/requirements.txt
COPY nr_ingest/ /app/nr_ingest/
COPY server/ /app/server/
CMD ["python", "/app/nr_ingest/scheduler.py"]
```

### `nr_ingest/scheduler.py` (new)

Entry point for the container. Behaviour:

1. On startup, validate that `NR_LICENSE_KEY` and `NR_ACCOUNT_ID` are present — exit with a clear error if either is missing.
2. Call `push_all_devices.main()` immediately.
3. Log the result (success with event count, or failure with exit code).
4. Sleep 300 seconds.
5. Repeat from step 2 indefinitely.

On push failure: log the error and continue — next run in 5 minutes is the retry. The container does not crash or restart due to a transient NR API error.

### `docker-compose.yml` (updated)

New service added:

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

No healthcheck needed — it's a fire-and-loop worker, not a service other containers depend on.

---

## What Is Not Changed

- `push_all_devices.py` — imported as a library, not modified
- `data_source.py` — fallback path works correctly inside the container
- `server/`, `simulator/`, `ui/` — untouched

---

## Local Setup

Add to `.env`:
```
NR_LICENSE_KEY=<your key>
NR_ACCOUNT_ID=<your account id>
```

Then `docker compose up --build` includes the scheduler automatically.

---

## Lightsail Deployment

Set `NR_LICENSE_KEY` and `NR_ACCOUNT_ID` as environment variables in the Lightsail container service deployment configuration. No `.env` file is used in production.
