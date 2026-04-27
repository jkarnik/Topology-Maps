"""Phase 1 validation: push one entity of each remaining type and print verification queries.

Skips the already-verified switch (LON138S-SW01).
Entity types covered:
  EXT-FIREWALL     — eventType KFirewall  + provider kentik-firewall
  EXT-ACCESS_POINT — eventType KAccessPoint + provider kentik-cisco-ap
  EXT-HOST         — eventType FlexSystemSample + displayName
  EXT-SITE         — eventType KNetwork + SiteID
  MERAKI_ORGANIZATION — eventType MerakiOrganization (skipped if orgId absent)
"""
import json
import os
import sys
from pathlib import Path

import httpx

from data_source import load_snapshot

PROJECT_ROOT = Path(__file__).parent.parent
NR_EVENT_API_US = "https://insights-collector.newrelic.com/v1/accounts/{account_id}/events"

_ENV_FILE = PROJECT_ROOT / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

SKIP_SWITCH = "LON138S-SW01"


def pick_one(nodes, node_type, exclude_name=None):
    for n in nodes:
        if n["type"] == node_type and n.get("name") != exclude_name:
            return n
    return None


def build_firewall_event(device: dict) -> dict:
    return {
        "eventType": "KFirewall",
        "provider": "kentik-firewall",
        "device_name": device["name"],
        "src_addr": device.get("ip") or "",
        "tags.vendor": "meraki",
        "tags.model": device.get("model") or "",
        "tags.serial": device["id"],
        "tags.mac": device.get("mac") or "",
        "tags.environment": "experimental",
        "tags.source": "topology-maps-app",
    }


def build_ap_event(device: dict) -> dict:
    return {
        "eventType": "KAccessPoint",
        "provider": "kentik-cisco-ap",
        "device_name": device["name"],
        "src_addr": device.get("ip") or "",
        "tags.vendor": "meraki",
        "tags.model": device.get("model") or "",
        "tags.serial": device["id"],
        "tags.mac": device.get("mac") or "",
        "tags.environment": "experimental",
        "tags.source": "topology-maps-app",
    }


def build_endpoint_event(device: dict) -> dict:
    return {
        "eventType": "FlexSystemSample",
        "displayName": device["name"],
        "src_addr": device.get("ip") or "",
        "tags.mac": device.get("mac") or "",
        "tags.environment": "experimental",
        "tags.source": "topology-maps-app",
    }


def build_site_event(network: dict) -> dict:
    return {
        "eventType": "KNetwork",
        "SiteID": network["name"],
        "tags.network_id": network["id"],
        "tags.environment": "experimental",
        "tags.source": "topology-maps-app",
    }


def build_org_event(org_id: str, org_name: str) -> dict:
    return {
        "eventType": "MerakiOrganization",
        "instrumentation.provider": "kentik",
        "instrumentation.name": "meraki.organization",
        "org_id": org_id,
        "org_name": org_name,
        "tags.environment": "experimental",
        "tags.source": "topology-maps-app",
    }


def main() -> int:
    license_key = os.environ.get("NR_LICENSE_KEY")
    account_id = os.environ.get("NR_ACCOUNT_ID")
    if not license_key or not account_id:
        print("ERROR: NR_LICENSE_KEY or NR_ACCOUNT_ID not set")
        return 1

    snapshot = load_snapshot()
    nodes = snapshot["topology"]["__all__"]["l2"]["nodes"]
    networks = snapshot["networks"]
    org_id = snapshot.get("orgId") or ""
    org_name = snapshot.get("orgName") or ""

    events = []  # list of (label, event)

    fw = pick_one(nodes, "firewall")
    if fw:
        events.append(("FIREWALL → EXT-FIREWALL", build_firewall_event(fw)))
    else:
        print("WARNING: no firewall node found")

    ap = pick_one(nodes, "access_point")
    if ap:
        events.append(("ACCESS_POINT → EXT-ACCESS_POINT", build_ap_event(ap)))
    else:
        print("WARNING: no access_point node found")

    ep = pick_one(nodes, "endpoint")
    if ep:
        events.append(("ENDPOINT → EXT-HOST", build_endpoint_event(ep)))
    else:
        print("WARNING: no endpoint node found")

    if networks:
        events.append(("NETWORK → EXT-SITE", build_site_event(networks[0])))
    else:
        print("WARNING: no networks found")

    if org_id:
        events.append(("ORG → MERAKI_ORGANIZATION", build_org_event(org_id, org_name)))
    else:
        print("WARNING: orgId not in snapshot — org entity skipped.")
        print("  Save a fresh topology snapshot from the UI to populate it.")

    print(f"\nSending {len(events)} events:\n")
    for label, event in events:
        print(f"  [{label}]")
        print(f"  {json.dumps(event, indent=4)}\n")

    url = NR_EVENT_API_US.format(account_id=account_id)
    headers = {"Api-Key": license_key, "Content-Type": "application/json"}
    payload = [e for _, e in events]
    resp = httpx.post(url, headers=headers, json=payload, timeout=10.0)
    print(f"Response: {resp.status_code} {resp.text}")

    if resp.status_code != 200:
        print("\nFAILED.")
        return 1

    print("\nSUCCESS. All events accepted.\n")
    print("Verification (wait 1-5 min for entity synthesis):")
    print(f"  Account: https://one.newrelic.com/nr1-core?account={account_id}\n")

    for label, event in events:
        et = event.get("eventType")
        name_field = (
            event.get("device_name")
            or event.get("displayName")
            or event.get("SiteID")
            or event.get("org_name")
        )
        print(f"  [{label}]")
        print(f"  NRQL: FROM {et} SELECT * WHERE {next(k for k in ('device_name','displayName','SiteID','org_name') if event.get(k))} = '{name_field}' SINCE 10 minutes ago")
        print()

    print("  Combined entity check:")
    print(f"  FROM Entity SELECT entityType, name WHERE `tags.source` = 'topology-maps-app' SINCE 10 minutes ago LIMIT 20")

    return 0


if __name__ == "__main__":
    sys.exit(main())
