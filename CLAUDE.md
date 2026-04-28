# Topology Maps — Project Context

## Commands

```bash
# Start full stack (simulator + server + UI)
docker compose up --build

# Run backend tests (289 tests, no Docker required)
python3 -m pytest

# UI dev server (hot reload, port 5173)
cd ui && npm run dev

# UI production build
cd ui && npm run build
```

## Architecture

Three Docker services, each on a fixed port:

| Service | Port | Role |
|---------|------|------|
| `simulator` | 8001 (REST), 10161-10167 (SNMP/UDP) | Fake SNMP agents + roaming simulator |
| `server` | 8000 | FastAPI + collector + WebSocket |
| `ui` | 80 | React + Vite + Tailwind + React Flow |

```
simulator ←SNMP── collector (runs inside server)
                       │
                    server ──WS──▶ ui
                       │
                  data/app.db (SQLite, volume-mounted)
```

WebSocket channels: `/ws/topology` (live topology), `/ws/config` (config sweep events)

## Key Files

- `server/main.py` — FastAPI app, lifespan hooks, WebSocket setup
- `server/db.py` — SQLite layer; `DB_PATH = data/app.db` (overridden in tests)
- `server/routes/` — REST routes (topology, devices, meraki, config, simulation, system)
- `server/config_collector/` — baseline sweep + change-log poller for Meraki config
- `collector/` — SNMP topology discovery (LLDP walk from FortiGate seed)
- `nr_ingest/` — New Relic push scripts (run locally, not in Docker)
- `ui/src/components/` — React components; `ConfigBrowser/` is the main config UI

## `nr_ingest/` Workflow

Scripts run outside Docker against the live SQLite DB:

1. `data_source.py` — copies DB from container (`topologymaps-server-1`) via `docker cp`; falls back to `data/app.db`
2. `push_all_devices.py` — full topology push
3. `create_relationships.py` / `create_workloads.py` — NR relationship + workload setup

Credentials read from `.env` at project root: `NR_API_KEY`, `NR_ACCOUNT_ID`.

## Constraints

- **Read-only from Meraki/vendor APIs.** Never write back to Meraki or any vendor API. Exports and observability only.
- `MERAKI_API_KEY` env var required for config collector; without it the config poller does not start.

## DB Gotcha

`server/db.py` sets `DB_PATH = Path("data/app.db")` as a module-level default. Tests monkeypatch `server.database.DB_PATH` to a temp dir — never rely on the live DB in tests.
