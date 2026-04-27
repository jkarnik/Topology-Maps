"""Create one NR Workload per Meraki network, dynamically populated by network_id tag."""
import json
import os
import sys
from pathlib import Path

import httpx

from data_source import load_snapshot

PROJECT_ROOT = Path(__file__).parent.parent
NR_GRAPHQL = "https://api.newrelic.com/graphql"

_ENV_FILE = PROJECT_ROOT / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

CREATE_WORKLOAD = """
mutation CreateWorkload($accountId: Int!, $name: String!, $query: String!) {
  workloadCreate(accountId: $accountId, workload: {
    name: $name
    entitySearchQueries: [{ query: $query }]
  }) {
    id
    name
    permalink
  }
}
"""


def create_workload(client, api_key, account_id, name, network_id):
    query = (
        f"tags.network_id = '{network_id}' AND tags.source = 'topology-maps-app'"
    )
    resp = client.post(
        NR_GRAPHQL,
        headers={"API-Key": api_key, "Content-Type": "application/json"},
        json={
            "query": CREATE_WORKLOAD,
            "variables": {
                "accountId": int(account_id),
                "name": name,
                "query": query,
            },
        },
        timeout=15.0,
    )
    resp.raise_for_status()
    body = resp.json()
    if "errors" in body:
        raise RuntimeError(body["errors"])
    return body["data"]["workloadCreate"]


def main():
    api_key = os.environ.get("NR_USER_API_KEY")
    account_id = os.environ.get("NR_ACCOUNT_ID")
    if not api_key or not account_id:
        print("ERROR: NR_USER_API_KEY or NR_ACCOUNT_ID not set")
        return 1

    snapshot = load_snapshot()
    networks = snapshot["networks"]
    print(f"Creating {len(networks)} workloads...\n")

    with httpx.Client() as client:
        for network in networks:
            name = network["name"]
            network_id = network["id"]
            try:
                result = create_workload(client, api_key, account_id, name, network_id)
                print(f"  ✓ {name}")
                print(f"    {result['permalink']}")
            except Exception as e:
                print(f"  ✗ {name}: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
