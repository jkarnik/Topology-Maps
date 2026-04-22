"""Single source of truth for Tier 1+2 Meraki config endpoints.

Every entry in `ENDPOINTS` represents one GET endpoint the collector
pulls. The scanner uses this catalog to enumerate URLs during a
baseline or anti-drift sweep. The change-log poller uses
`event_to_endpoints()` to map a change event to the endpoints it
affects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Scope = Literal["org", "network", "device", "ssid"]


@dataclass(frozen=True)
class EndpointSpec:
    """One Meraki config endpoint.

    Fields
    ------
    config_area   : stable canonical key used as config_observations.config_area
    scope         : 'org' | 'network' | 'device' | 'ssid'
    url_template  : relative URL with {org_id}/{network_id}/{serial}/{ssid_number} placeholders
    product_filter: tuple of Meraki product-type strings; () means no filter
    tier          : 1 or 2 (informational; both are collected in Phase 1)
    paginated     : True if response requires Link-header pagination
    """
    config_area: str
    scope: Scope
    url_template: str
    product_filter: tuple[str, ...]
    tier: int
    paginated: bool


from server.config_collector._endpoints_org import ORG_ENDPOINTS
from server.config_collector._endpoints_network import NETWORK_ENDPOINTS
from server.config_collector._endpoints_device import DEVICE_ENDPOINTS

# Aggregate list of every endpoint the collector knows about.
# More tuples will be added in subsequent tasks (_endpoints_device).
ENDPOINTS: tuple[EndpointSpec, ...] = ORG_ENDPOINTS + NETWORK_ENDPOINTS + DEVICE_ENDPOINTS


from typing import Iterator


def _network_matches(spec: EndpointSpec, network: dict) -> bool:
    """Product-type filter check for a network-scoped endpoint."""
    if not spec.product_filter:
        return True
    return any(p in (network.get("productTypes") or []) for p in spec.product_filter)


def _device_matches(spec: EndpointSpec, device: dict) -> bool:
    if not spec.product_filter:
        return True
    return device.get("productType") in spec.product_filter


def expand_for_org(
    org_id: str,
    networks: list[dict],
    devices_by_network: dict[str, list[dict]],
    enabled_ssids_by_network: dict[str, list[int]],
) -> Iterator[dict]:
    """Yield concrete URL jobs the scanner must fetch.

    Each yielded dict has keys:
      - url         : relative URL with placeholders resolved
      - config_area : canonical key for config_observations
      - scope       : 'org' | 'network' | 'device' | 'ssid'
      - entity_type : storage-layer entity_type
      - entity_id   : storage-layer entity_id
      - sub_key     : optional (e.g. ssid_number as str)
      - paginated   : bool
    """
    for spec in ENDPOINTS:
        if spec.scope == "org":
            yield {
                "url": spec.url_template.format(org_id=org_id),
                "config_area": spec.config_area,
                "scope": "org",
                "entity_type": "org",
                "entity_id": org_id,
                "sub_key": None,
                "paginated": spec.paginated,
            }

        elif spec.scope == "network":
            for net in networks:
                if not _network_matches(spec, net):
                    continue
                yield {
                    "url": spec.url_template.format(network_id=net["id"]),
                    "config_area": spec.config_area,
                    "scope": "network",
                    "entity_type": "network",
                    "entity_id": net["id"],
                    "sub_key": None,
                    "paginated": spec.paginated,
                }

        elif spec.scope == "ssid":
            for net in networks:
                if "wireless" not in (net.get("productTypes") or []):
                    continue
                for n in enabled_ssids_by_network.get(net["id"], []):
                    yield {
                        "url": spec.url_template.format(network_id=net["id"], ssid_number=n),
                        "config_area": spec.config_area,
                        "scope": "ssid",
                        "entity_type": "ssid",
                        "entity_id": f"{net['id']}:{n}",
                        "sub_key": str(n),
                        "paginated": spec.paginated,
                    }

        elif spec.scope == "device":
            for net in networks:
                for dev in devices_by_network.get(net["id"], []):
                    if not _device_matches(spec, dev):
                        continue
                    yield {
                        "url": spec.url_template.format(serial=dev["serial"]),
                        "config_area": spec.config_area,
                        "scope": "device",
                        "entity_type": "device",
                        "entity_id": dev["serial"],
                        "sub_key": None,
                        "paginated": spec.paginated,
                    }
