"""Phase 1 debug: push test events with different shapes to verify which land in NRDB."""
import json
import sys
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

NR_EVENT_API_US = "https://insights-collector.newrelic.com/v1/accounts/{account_id}/events"


def load_env(path: Path) -> dict[str, str]:
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def main() -> int:
    env = load_env(ENV_FILE)
    license_key = env["NR_LICENSE_KEY"]
    account_id = env["NR_ACCOUNT_ID"]

    # Use a clearly-unique device name so we can tell our entity apart from any pre-existing one.
    unique_name = "TOPOLOGY-MAPS-TEST-SWITCH-001"

    events = [
        # Event 1: original shape
        {
            "eventType": "KSwitch",
            "provider": "kentik-switch",
            "device_name": unique_name,
            "src_addr": "10.99.99.1",
            "tags.source": "topology-maps-app",
            "tags.test_marker": "phase1-debug",
        },
        # Event 2: alternative eventType (non-K-prefix) in case "KSwitch" is reserved
        {
            "eventType": "MerakiTopologyTest",
            "provider": "kentik-switch",
            "device_name": unique_name,
            "src_addr": "10.99.99.1",
            "tags.source": "topology-maps-app",
            "tags.test_marker": "phase1-debug",
        },
    ]

    url = NR_EVENT_API_US.format(account_id=account_id)
    headers = {"Api-Key": license_key, "Content-Type": "application/json"}

    print(f"POSTing {len(events)} events to {url}")
    print(json.dumps(events, indent=2))

    resp = httpx.post(url, headers=headers, json=events, timeout=10.0)
    print(f"\nResponse: {resp.status_code} {resp.text}")

    if resp.status_code != 200:
        return 1

    print("\nWait 1-2 minutes, then run these NRQL queries:")
    print(f"  1. SHOW EVENT TYPES SINCE 10 minutes ago")
    print(f"  2. FROM KSwitch SELECT * WHERE device_name = '{unique_name}' SINCE 10 minutes ago")
    print(f"  3. FROM MerakiTopologyTest SELECT * WHERE device_name = '{unique_name}' SINCE 10 minutes ago")
    print(f"\nIn Entity Explorer, search for: {unique_name}")
    print(f"  If this synthesizes a new entity, our event pipeline is confirmed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
