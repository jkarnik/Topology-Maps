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

LIST_WORKLOADS = """
query ListWorkloads($accountId: Int!) {
  actor {
    account(id: $accountId) {
      workload {
        collections {
          guid
          name
          entitySearchQueries { query }
        }
      }
    }
  }
}
"""

UPDATE_WORKLOAD = """
mutation UpdateWorkload($guid: EntityGuid!, $q1: String!, $q2: String!) {
  workloadUpdate(guid: $guid, workload: {
    entitySearchQueries: [{ query: $q1 }, { query: $q2 }]
  }) {
    guid
    name
  }
}
"""

ENTITY_QUERY_BASE = "tags.network_id = '{network_id}' AND tags.source = 'topology-maps-app'"
# Two queries ORed by NR: devices+site, then switch ports (excludes VLANs)
ENTITY_QUERY_NO_VLANS_DEVICES = "tags.network_id = '{network_id}' AND tags.source = 'topology-maps-app' AND type IN ('FIREWALL', 'SWITCH', 'ACCESS_POINT', 'HOST', 'SITE')"
ENTITY_QUERY_NO_VLANS_PORTS = "tags.network_id = '{network_id}' AND tags.source = 'topology-maps-app' AND tags.subtype = 'switch_port'"


def nerdgraph(client, api_key, query, variables=None):
    resp = client.post(
        NR_GRAPHQL,
        headers={"API-Key": api_key, "Content-Type": "application/json"},
        json={"query": query, "variables": variables or {}},
        timeout=15.0,
    )
    resp.raise_for_status()
    body = resp.json()
    if "errors" in body:
        raise RuntimeError(body["errors"])
    return body["data"]


def create_workload(client, api_key, account_id, name, network_id):
    query = ENTITY_QUERY_BASE.format(network_id=network_id)
    data = nerdgraph(client, api_key, CREATE_WORKLOAD, {
        "accountId": int(account_id),
        "name": name,
        "query": query,
    })
    return data["workloadCreate"]


def fetch_workloads(client, api_key, account_id):
    data = nerdgraph(client, api_key, LIST_WORKLOADS, {"accountId": int(account_id)})
    return data["actor"]["account"]["workload"]["collections"]


def update_workload_query(client, api_key, workload_guid, q1, q2):
    data = nerdgraph(client, api_key, UPDATE_WORKLOAD, {"guid": workload_guid, "q1": q1, "q2": q2})
    return data["workloadUpdate"]


def main():
    api_key = os.environ.get("NR_USER_API_KEY")
    account_id = os.environ.get("NR_ACCOUNT_ID")
    if not api_key or not account_id:
        print("ERROR: NR_USER_API_KEY or NR_ACCOUNT_ID not set")
        return 1

    args = sys.argv[1:]
    site_filter = None
    exclude_vlans = "--exclude-vlans" in args
    if "--site" in args:
        idx = args.index("--site")
        if idx + 1 >= len(args):
            print("ERROR: --site requires a value, e.g. --site BLR")
            return 1
        site_filter = args[idx + 1]

    if exclude_vlans:
        snapshot = load_snapshot()
        networks_by_name = {n["name"]: n for n in snapshot["networks"]}
        with httpx.Client() as client:
            workloads = fetch_workloads(client, api_key, account_id)
            targets = [
                w for w in workloads
                if w["name"] in networks_by_name
                and (not site_filter or site_filter.lower() in w["name"].lower())
            ]
            print(f"Updating {len(targets)} workload(s) to exclude VLANs...\n")
            for w in targets:
                net = networks_by_name[w["name"]]
                q1 = ENTITY_QUERY_NO_VLANS_DEVICES.format(network_id=net["id"])
                q2 = ENTITY_QUERY_NO_VLANS_PORTS.format(network_id=net["id"])
                try:
                    update_workload_query(client, api_key, w["guid"], q1, q2)
                    print(f"  ✓ {w['name']}")
                except Exception as e:
                    print(f"  ✗ {w['name']}: {e}")
        return 0

    snapshot = load_snapshot()
    networks = snapshot["networks"]
    if site_filter:
        networks = [n for n in networks if site_filter.lower() in n["name"].lower()]
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
