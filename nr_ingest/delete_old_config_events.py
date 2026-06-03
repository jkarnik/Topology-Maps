# nr_ingest/delete_old_config_events.py
"""Delete MerakiConfigSnapshot and MerakiConfigChange events from NR that predate
a given cutoff timestamp, using NerdGraph historicalDataDeleteCreate.

Usage:
    python3 nr_ingest/delete_old_config_events.py                 # cutoff = now
    python3 nr_ingest/delete_old_config_events.py --before 2026-06-03T00:00:00Z
    python3 nr_ingest/delete_old_config_events.py --dry-run       # preview only
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

_DIR = Path(__file__).parent
_PROJECT_ROOT = _DIR.parent

_ENV_FILE = _PROJECT_ROOT / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

NR_GRAPHQL_API = "https://api.newrelic.com/graphql"

EVENT_TYPES = ["MerakiConfigSnapshot", "MerakiConfigChange"]

_CREATE_MUTATION = """
mutation($accountId: Int!, $nrql: String!) {
  historicalDataDeleteCreate(
    accountId: $accountId
    deleteConditions: { nrql: $nrql }
  ) {
    id
    status
    error
  }
}
"""

_STATUS_QUERY = """
query($accountId: Int!, $deleteId: ID!) {
  actor {
    account(id: $accountId) {
      historicalDataDelete(id: $deleteId) {
        id
        status
        error
      }
    }
  }
}
"""


def _graphql(user_api_key: str, body: dict) -> dict:
    resp = httpx.post(
        NR_GRAPHQL_API,
        headers={"Api-Key": user_api_key, "Content-Type": "application/json"},
        json=body,
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


def create_delete_job(account_id: int, user_api_key: str, nrql: str) -> dict:
    result = _graphql(user_api_key, {
        "query": _CREATE_MUTATION,
        "variables": {"accountId": account_id, "nrql": nrql},
    })
    errors = result.get("errors")
    if errors:
        raise RuntimeError(f"NerdGraph error: {errors}")
    return result["data"]["historicalDataDeleteCreate"]


def check_status(account_id: int, user_api_key: str, delete_id: str) -> dict:
    result = _graphql(user_api_key, {
        "query": _STATUS_QUERY,
        "variables": {"accountId": account_id, "deleteId": delete_id},
    })
    errors = result.get("errors")
    if errors:
        raise RuntimeError(f"NerdGraph error: {errors}")
    return result["data"]["actor"]["account"]["historicalDataDelete"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete old Meraki config events from NR")
    parser.add_argument(
        "--before",
        default=None,
        help="ISO UTC cutoff timestamp (default: now). Events older than this are deleted.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the NRQL conditions without submitting deletion jobs.",
    )
    args = parser.parse_args()

    user_api_key = os.environ.get("NR_USER_API_KEY")
    account_id_str = os.environ.get("NR_ACCOUNT_ID")
    if not user_api_key or not account_id_str:
        missing = [k for k in ("NR_USER_API_KEY", "NR_ACCOUNT_ID") if not os.environ.get(k)]
        print(f"ERROR: missing required env vars: {', '.join(missing)}", file=sys.stderr)
        return 1

    account_id = int(account_id_str)

    if args.before:
        cutoff = datetime.fromisoformat(args.before.replace("Z", "+00:00"))
    else:
        cutoff = datetime.now(tz=timezone.utc)

    # NerdGraph historicalDataDeleteCreate uses epoch milliseconds in NRQL
    cutoff_ms = int(cutoff.timestamp() * 1000)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"Cutoff: {cutoff_str} ({cutoff_ms} ms)")
    print()

    for event_type in EVENT_TYPES:
        nrql = f"FROM {event_type} SELECT * WHERE timestamp < {cutoff_ms}"
        print(f"  Event type : {event_type}")
        print(f"  NRQL       : {nrql}")

        if args.dry_run:
            print("  [dry-run] Skipping submission.\n")
            continue

        try:
            job = create_delete_job(account_id, user_api_key, nrql)
        except Exception as e:
            print(f"  ERROR: {e}\n", file=sys.stderr)
            continue

        if job.get("error"):
            print(f"  ERROR from NR: {job['error']}\n", file=sys.stderr)
            continue

        print(f"  Job ID     : {job['id']}")
        print(f"  Status     : {job['status']}")
        print(f"  (Deletion runs asynchronously — check status with --status-id {job['id']})\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
