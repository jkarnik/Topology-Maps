"""Create user-defined entity relationships in New Relic for the Meraki topology.

Reads entity GUIDs from NerdGraph, then fires batched
entityRelationshipUserDefinedCreateOrReplace mutations to wire up:
  - Site CONTAINS Firewall / Switch / AP
  - Site CONTAINS VLAN
  - Switch CONTAINS Port
  - Switch / Firewall CONNECTS_TO Switch / Firewall  (LLDP edges)
  - Client CONNECTS_TO AP
"""
import os
import sys
from pathlib import Path
from typing import NamedTuple, Optional

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

BATCH_SIZE = 25  # relationships per mutation call

ENTITY_SEARCH_GQL = """
query SearchEntities($query: String!, $cursor: String) {
  actor {
    entitySearch(query: $query) {
      results(cursor: $cursor) {
        entities {
          guid
          name
          entityType
          tags { key values }
        }
        nextCursor
      }
    }
  }
}
"""


class Rel(NamedTuple):
    source_guid: str
    target_guid: str
    rel_type: str  # CONTAINS | CONNECTS_TO


def nerdgraph(client: httpx.Client, api_key: str, query: str, variables: Optional[dict] = None) -> dict:
    resp = client.post(
        NR_GRAPHQL,
        headers={"API-Key": api_key, "Content-Type": "application/json"},
        json={"query": query, "variables": variables or {}},
        timeout=30.0,
    )
    resp.raise_for_status()
    body = resp.json()
    if "errors" in body:
        raise RuntimeError(body["errors"])
    return body["data"]


def fetch_all_entities(client: httpx.Client, api_key: str) -> list[dict]:
    entities: list[dict] = []
    cursor = None
    while True:
        data = nerdgraph(client, api_key, ENTITY_SEARCH_GQL, {
            "query": "tags.source = 'topology-maps-app'",
            "cursor": cursor,
        })
        results = data["actor"]["entitySearch"]["results"]
        entities.extend(results["entities"])
        cursor = results.get("nextCursor")
        if not cursor:
            break
    return entities


def _tag(entity: dict, key: str) -> str:
    """Return the first value of a tag key, or empty string."""
    for tag in entity.get("tags", []):
        if tag["key"] == key:
            return tag["values"][0] if tag["values"] else ""
    return ""


def build_lookup_maps(entities: list[dict]) -> tuple[dict, dict, dict]:
    """Return (guid_by_name, guid_by_serial, site_guid_by_network_id).

    NerdGraph returns all EXT-* entities as entityType=EXTERNAL_ENTITY, so we
    distinguish entity roles by tag presence rather than entityType:
      - has 'serial' tag           → device (switch / firewall / AP)
      - has 'network_id', no 'serial', no 'subtype', no 'mac' → site
      - everything else            → VLAN / port / client (looked up by name)
    """
    guid_by_name: dict[str, str] = {}
    guid_by_serial: dict[str, str] = {}
    site_guid_by_network_id: dict[str, str] = {}

    for e in entities:
        guid = e["guid"]
        guid_by_name[e["name"]] = guid

        tags = {t["key"]: (t["values"][0] if t["values"] else "") for t in e.get("tags", [])}
        serial = tags.get("serial", "")
        if serial:
            guid_by_serial[serial] = guid
            continue

        net_id = tags.get("network_id", "")
        if net_id and not tags.get("subtype") and not tags.get("mac"):
            site_guid_by_network_id[net_id] = guid

    return guid_by_name, guid_by_serial, site_guid_by_network_id


def generate_relationships(
    snapshot: dict,
    guid_by_name: dict,
    guid_by_serial: dict,
    site_guid_by_network_id: dict,
) -> list[Rel]:
    rels: list[Rel] = []
    topo = snapshot["topology"]
    nodes = topo["__all__"]["l2"]["nodes"]
    edges = topo["__all__"]["l2"]["edges"]
    subnets = topo["__all__"]["l3"]["subnets"]

    device_types = {"firewall", "floor_switch", "core_switch", "access_point"}

    # Site CONTAINS Firewall / Switch / AP
    for node in nodes:
        if node["type"] not in device_types:
            continue
        site_guid = site_guid_by_network_id.get(node.get("network_id") or "")
        device_guid = guid_by_name.get(node["name"])
        if site_guid and device_guid:
            rels.append(Rel(site_guid, device_guid, "CONTAINS"))

    # Site CONTAINS VLAN
    for subnet in subnets:
        net_id = subnet.get("network_id") or ""
        site_guid = site_guid_by_network_id.get(net_id)
        vlan_guid = guid_by_name.get(f"vlan-{net_id}-{subnet['vlan']}")
        if site_guid and vlan_guid:
            rels.append(Rel(site_guid, vlan_guid, "CONTAINS"))

    # Switch CONTAINS Port
    for net_key, net_topo in topo.items():
        if net_key == "__all__":
            continue
        for serial, dev_detail in net_topo.get("deviceDetails", {}).items():
            switch_guid = guid_by_serial.get(serial)
            if not switch_guid:
                continue
            for port in dev_detail.get("switch_ports", []):
                port_guid = guid_by_name.get(f"port-{serial}-{port['portId']}")
                if port_guid:
                    rels.append(Rel(switch_guid, port_guid, "CONTAINS"))

    # Switch / Firewall CONNECTS_TO Switch / Firewall  (LLDP)
    seen_pairs: set[frozenset] = set()
    for edge in edges:
        src_guid = guid_by_serial.get(edge["source"])
        tgt_guid = guid_by_serial.get(edge["target"])
        if not src_guid or not tgt_guid or src_guid == tgt_guid:
            continue
        pair = frozenset({src_guid, tgt_guid})
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        rels.append(Rel(src_guid, tgt_guid, "CONNECTS_TO"))

    # Client CONNECTS_TO AP  (connected_ap field stores the AP's serial)
    for node in nodes:
        if node["type"] != "endpoint":
            continue
        ap_serial = node.get("connected_ap") or ""
        if not ap_serial:
            continue
        client_name = node.get("name") or node.get("id") or ""
        client_guid = guid_by_name.get(client_name)
        ap_guid = guid_by_serial.get(ap_serial)
        if client_guid and ap_guid:
            rels.append(Rel(client_guid, ap_guid, "CONNECTS_TO"))

    return rels


def _batch_mutation(batch: list[Rel]) -> str:
    """Build a single mutation with one aliased field per relationship."""
    fields = "\n".join(
        f'  r{i}: entityRelationshipUserDefinedCreateOrReplace('
        f'sourceEntityGuid: "{r.source_guid}", '
        f'targetEntityGuid: "{r.target_guid}", '
        f'type: {r.rel_type}) {{ errors {{ message type }} }}'
        for i, r in enumerate(batch)
    )
    return f"mutation {{\n{fields}\n}}"


def post_batch(client: httpx.Client, api_key: str, batch: list[Rel]) -> list[str]:
    """Fire one batch mutation. Returns error messages (empty = success)."""
    data = nerdgraph(client, api_key, _batch_mutation(batch))
    return [
        f"r{i}: {err['message']}"
        for i, r in enumerate(batch)
        for err in (data.get(f"r{i}") or {}).get("errors") or []
    ]


def chunked(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def main() -> int:
    api_key = os.environ.get("NR_USER_API_KEY")
    if not api_key:
        print("ERROR: NR_USER_API_KEY not set")
        return 1

    print("Loading snapshot...")
    snapshot = load_snapshot()

    with httpx.Client() as client:
        print("Fetching entity GUIDs from New Relic...")
        entities = fetch_all_entities(client, api_key)
        print(f"  Found {len(entities)} entities")

        guid_by_name, guid_by_serial, site_guid_by_network_id = build_lookup_maps(entities)
        print(f"  Sites by network_id: {len(site_guid_by_network_id)}")
        print(f"  Devices by serial:   {len(guid_by_serial)}")
        print(f"  Entities by name:    {len(guid_by_name)}")

        print("\nGenerating relationships...")
        rels = generate_relationships(snapshot, guid_by_name, guid_by_serial, site_guid_by_network_id)

        by_type: dict[str, int] = {}
        for r in rels:
            by_type[r.rel_type] = by_type.get(r.rel_type, 0) + 1
        for t, c in sorted(by_type.items()):
            print(f"  {t}: {c}")
        print(f"  Total: {len(rels)}")

        if not rels:
            print("\nNo relationships to create — check that entities are synthesized and GUIDs resolved.")
            return 0

        print(f"\nCreating {len(rels)} relationships in batches of {BATCH_SIZE}...")
        total_errors = 0
        for batch_num, batch in enumerate(chunked(rels, BATCH_SIZE), start=1):
            errs = post_batch(client, api_key, batch)
            status = f"OK" if not errs else f"{len(errs)} errors"
            print(f"  Batch {batch_num:3d} ({len(batch):3d} rels) — {status}")
            for err in errs:
                print(f"    ERROR: {err}")
            total_errors += len(errs)

    if total_errors:
        print(f"\nCompleted with {total_errors} errors.")
        return 1

    print(f"\nAll {len(rels)} relationships created.")
    print("\nVerify in a Workload — open any Workload, click the Map tab.")
    print("Expected: devices connected by lines representing L2 topology.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
