"""Phase 2: Push all entities to NR — devices, networks, org, clients, VLANs, switch ports."""
import json
import os
import sys
from pathlib import Path

import httpx

from data_source import load_snapshot

_ENV_FILE = Path(__file__).parent.parent / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

NR_EVENT_API_US = "https://insights-collector.newrelic.com/v1/accounts/{account_id}/events"

PROVIDER_BY_TYPE = {
    "firewall": "kentik-firewall",
    "floor_switch": "kentik-switch",
    "core_switch": "kentik-switch",
    "access_point": "kentik-cisco-ap",
}

EVENTTYPE_BY_TYPE = {
    "firewall": "KFirewall",
    "floor_switch": "KSwitch",
    "core_switch": "KSwitch",
    "access_point": "KAccessPoint",
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


def build_device_event(device: dict, networks_by_id: dict) -> dict:
    net = networks_by_id.get(device.get("network_id") or "", {})
    return {
        "eventType": EVENTTYPE_BY_TYPE[device["type"]],
        "provider": PROVIDER_BY_TYPE[device["type"]],
        "device_name": device["name"],
        "src_addr": device.get("ip") or "",
        "tags.vendor": "meraki",
        "tags.device_type": device["type"],
        "tags.model": device.get("model") or "",
        "tags.serial": device["id"],
        "tags.mac": device.get("mac") or "",
        "tags.firmware": device.get("firmware") or "",
        "tags.status": device.get("status") or "",
        "tags.public_ip": device.get("public_ip") or "",
        "tags.address": device.get("address") or "",
        "tags.ip_type": device.get("ip_type") or "",
        "tags.stack_name": device.get("stack_name") or "",
        "tags.stack_role": device.get("stack_role") or "",
        "tags.network_id": device.get("network_id") or "",
        "tags.network_name": net.get("name") or "",
        "tags.dashboard_url": device.get("dashboard_url") or "",
        "tags.environment": "experimental",
        "tags.source": "topology-maps-app",
    }


def build_site_event(network: dict) -> dict:
    return {
        "eventType": "KNetwork",
        "SiteID": network["name"],  # unique within this org; becomes entity name
        "tags.network_id": network["id"],
        "tags.network_name": network["name"],
        "tags.product_types": ",".join(network.get("productTypes") or []),
        "tags.environment": "experimental",
        "tags.source": "topology-maps-app",
    }


def build_client_event(endpoint: dict, networks_by_id: dict) -> dict:
    net = networks_by_id.get(endpoint.get("network_id") or "", {})
    return {
        "eventType": "FlexSystemSample",
        "displayName": endpoint["name"] or endpoint["id"],
        "src_addr": endpoint.get("ip") or "",
        "tags.mac": endpoint.get("mac") or "",
        "tags.vlan": endpoint.get("vlan") or "",
        "tags.connected_ap": endpoint.get("connected_ap") or "",
        "tags.network_id": endpoint.get("network_id") or "",
        "tags.network_name": net.get("name") or "",
        "tags.environment": "experimental",
        "tags.source": "topology-maps-app",
    }


def build_vlan_event(subnet: dict) -> dict:
    return {
        "eventType": "MerakiVlan",
        "service_name": f"vlan-{subnet['network_id']}-{subnet['vlan']}",
        "tags.subtype": "vlan",
        "tags.vlan_id": subnet.get("vlan") or "",
        "tags.vlan_name": subnet.get("name") or "",
        "tags.cidr": subnet.get("cidr") or "",
        "tags.gateway": subnet.get("gateway") or "",
        "tags.network_id": subnet.get("network_id") or "",
        "tags.environment": "experimental",
        "tags.source": "topology-maps-app",
    }


def build_port_event(serial: str, port: dict, network_id: str) -> dict:
    return {
        "eventType": "MerakiSwitchPort",
        "service_name": f"port-{serial}-{port['portId']}",
        "tags.subtype": "switch_port",
        "tags.port_id": port.get("portId") or "",
        "tags.switch_serial": serial,
        "tags.enabled": port.get("enabled", False),
        "tags.status": port.get("status") or "",
        "tags.is_uplink": port.get("isUplink", False),
        "tags.network_id": network_id,
        "tags.environment": "experimental",
        "tags.source": "topology-maps-app",
    }


def chunked(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def post_events(url, headers, events):
    resp = httpx.post(url, headers=headers, json=events, timeout=30.0)
    return resp


def main() -> int:
    license_key = os.environ["NR_LICENSE_KEY"]
    account_id = os.environ["NR_ACCOUNT_ID"]

    snapshot = load_snapshot()
    org_id: str = snapshot.get("orgId") or ""
    org_name: str = snapshot.get("orgName") or ""

    if not org_id:
        print("WARNING: orgId not in snapshot — org entity will be skipped.")
        print("  Run a topology refresh and save snapshot first to populate it.")
        org_events: list[dict] = []
    else:
        org_events = [build_org_event(org_id, org_name)]
        print(f"Org: {org_name} (id={org_id})")

    networks = snapshot["networks"]
    networks_by_id = {n["id"]: n for n in networks}
    topology = snapshot["topology"]
    if "__all__" not in topology:
        print(f"ERROR: no '__all__' aggregated topology in cache. Found keys: {list(topology.keys())}")
        return 1
    nodes = topology["__all__"]["l2"]["nodes"]

    devices = [n for n in nodes if n["type"] in PROVIDER_BY_TYPE]
    device_events = [build_device_event(d, networks_by_id) for d in devices]
    site_events = [build_site_event(n) for n in networks]

    endpoints = [n for n in nodes if n["type"] == "endpoint"]
    client_events = [build_client_event(e, networks_by_id) for e in endpoints]

    subnets = topology["__all__"]["l3"]["subnets"]
    vlan_events = [build_vlan_event(s) for s in subnets]

    port_events = []
    for net_key, net_topo in topology.items():
        if net_key == "__all__":
            continue
        for serial, dev_detail in net_topo.get("deviceDetails", {}).items():
            net_id = next(
                (n["network_id"] for n in devices if n["id"] == serial), ""
            )
            for port in dev_detail.get("switch_ports", []):
                port_events.append(build_port_event(serial, port, net_id))

    counts_by_type = {}
    for d in devices:
        counts_by_type[d["type"]] = counts_by_type.get(d["type"], 0) + 1
    print("Device counts:")
    for t, c in sorted(counts_by_type.items()):
        print(f"  {t}: {c}")
    print(f"Networks (sites): {len(site_events)}")
    print(f"Clients:          {len(client_events)}")
    print(f"VLANs:            {len(vlan_events)}")
    print(f"Switch ports:     {len(port_events)}")
    print(f"Total events to send: {len(org_events) + len(device_events) + len(site_events) + len(client_events) + len(vlan_events) + len(port_events)}")

    # Check device name uniqueness
    names = [d["name"] for d in devices]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        print(f"\nWARNING: duplicate device names detected: {dupes}")
        print("Entities with the same device_name will collide. Investigate before proceeding.")

    url = NR_EVENT_API_US.format(account_id=account_id)
    headers = {"Api-Key": license_key, "Content-Type": "application/json"}

    all_events = org_events + device_events + site_events + client_events + vlan_events + port_events
    total_sent = 0
    for batch_num, batch in enumerate(chunked(all_events, 500), start=1):
        print(f"\nBatch {batch_num}: posting {len(batch)} events...")
        resp = post_events(url, headers, batch)
        print(f"  Response: {resp.status_code} {resp.text}")
        if resp.status_code != 200:
            print("  FAILED - aborting")
            return 1
        total_sent += len(batch)

    print(f"\nAll {total_sent} events accepted by NR.")
    print("\nVerification steps (wait 2-5 min for synthesis):")
    print(f"  1. NRQL (count by type): FROM Entity SELECT uniqueCount(guid) WHERE `tags.source` = 'topology-maps-app' FACET entityType SINCE 10 minutes ago")
    print(f"     Expected: 1 org, 11 firewalls, 21 switches, 117 APs, 10 sites, ~147 hosts, 81 VLANs, 1034 ports")
    print(f"  2. Raw events: FROM MerakiVlan, MerakiSwitchPort, FlexSystemSample SELECT count(*) FACET eventType SINCE 10 minutes ago")
    return 0


if __name__ == "__main__":
    sys.exit(main())
