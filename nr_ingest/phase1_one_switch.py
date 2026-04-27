"""Phase 1: Push ONE switch to New Relic as an EXT-SWITCH entity and verify."""
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


def build_switch_event(switch: dict) -> dict:
    return {
        "eventType": "KSwitch",
        "provider": "kentik-switch",
        "device_name": switch["name"],
        "src_addr": switch.get("ip") or "",
        "tags.vendor": "meraki",
        "tags.model": switch.get("model") or "",
        "tags.serial": switch["id"],
        "tags.mac": switch.get("mac") or "",
        "tags.firmware": switch.get("firmware") or "",
        "tags.network_id": switch.get("network_id") or "",
        "tags.environment": "experimental",
        "tags.source": "topology-maps-app",
    }


def main() -> int:
    license_key = os.environ.get("NR_LICENSE_KEY")
    account_id = os.environ.get("NR_ACCOUNT_ID")
    if not license_key or not account_id:
        print("ERROR: NR_LICENSE_KEY or NR_ACCOUNT_ID not set in environment")
        return 1

    snapshot = load_snapshot()
    nodes = snapshot["topology"]["__all__"]["l2"]["nodes"]
    switches = [n for n in nodes if n["type"] == "floor_switch"]
    if not switches:
        print("ERROR: no switches found in seed data")
        return 1

    switch = switches[0]
    print(f"Picked switch: {switch['name']}")
    print(f"  serial: {switch['id']}")
    print(f"  ip:     {switch.get('ip')}")
    print(f"  model:  {switch.get('model')}")

    event = build_switch_event(switch)
    print(f"\nEvent payload:\n{json.dumps(event, indent=2)}")

    url = NR_EVENT_API_US.format(account_id=account_id)
    headers = {"Api-Key": license_key, "Content-Type": "application/json"}
    print(f"\nPOSTing to: {url}")
    resp = httpx.post(url, headers=headers, json=[event], timeout=10.0)
    print(f"Response: {resp.status_code} {resp.text}")

    if resp.status_code != 200:
        print("\nFAILED. Common causes: wrong region (try EU endpoint), bad key, wrong account ID.")
        return 1

    print("\nSUCCESS. Event accepted by NR.")
    print("\nTo verify entity synthesis (wait 1-5 minutes):")
    print(f"  1. Open https://one.newrelic.com/nr1-core?account={account_id}")
    print(f"  2. Go to 'All entities' or Entity Explorer")
    print(f"  3. Search for: {switch['name']}")
    print(f"  4. Expected entity type: EXT-SWITCH / Switch")
    print("\nOr via NRQL query:")
    print(f"  FROM KSwitch SELECT * WHERE device_name = '{switch['name']}' SINCE 10 minutes ago")
    return 0


if __name__ == "__main__":
    sys.exit(main())
