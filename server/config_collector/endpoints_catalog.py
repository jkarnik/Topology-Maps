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


# Dashboard page-prefix → set of config_areas to re-pull.
# More entries will be added as real Meraki pages are observed; the
# poller logs WARN on unmapped pages so the gap is visible.
_PAGE_PREFIX_MAP: dict[str, set[str]] = {
    "Security & SD-WAN > Addressing & VLANs": {
        "appliance_vlans", "appliance_vlans_settings", "appliance_single_lan",
    },
    "Security & SD-WAN > Firewall": {
        "appliance_firewall_l3", "appliance_firewall_l7",
        "appliance_firewall_inbound", "appliance_firewall_port_forwarding",
        "appliance_firewall_one_to_one_nat", "appliance_firewall_one_to_many_nat",
    },
    "Security & SD-WAN > Content filtering": {"appliance_content_filtering"},
    "Security & SD-WAN > Threat protection": {"appliance_security_intrusion", "appliance_security_malware"},
    "Security & SD-WAN > SD-WAN & traffic shaping": {
        "appliance_traffic_shaping_rules", "appliance_uplink_bandwidth", "appliance_uplink_selection",
    },
    "Security & SD-WAN > Site-to-site VPN": {"appliance_site_to_site_vpn", "appliance_vpn_bgp"},
    "Security & SD-WAN > Static routes": {"appliance_static_routes"},
    "Switch > Switch settings": {"switch_settings", "switch_stp", "switch_mtu"},
    "Switch > ACL": {"switch_acls"},
    "Switch > Access policies": {"switch_access_policies"},
    "Switch > QoS": {"switch_qos_rules", "switch_qos_order", "switch_dscp_to_cos"},
    "Switch > Stacks": {"switch_stacks"},
    "Switch > Link aggregation": {"switch_link_aggregations"},
    "Switch > DHCP servers & ARP": {"switch_dhcp_server_policy"},
    "Wireless > SSIDs": {"wireless_ssids"},
    "Wireless > Access Control": {"wireless_ssids", "wireless_ssid_traffic_shaping"},
    "Wireless > Firewall & traffic shaping": {
        "wireless_ssid_l3_firewall", "wireless_ssid_l7_firewall", "wireless_ssid_traffic_shaping",
    },
    "Wireless > RF profiles": {"wireless_rf_profiles"},
    "Network-wide > General": {"network_metadata", "network_settings"},
    "Network-wide > Alerts": {"network_alerts_settings"},
    "Network-wide > Group policies": {"network_group_policies"},
    "Organization > Administrators": {"org_admins", "org_saml_roles"},
    "Organization > Configuration templates": {"org_config_templates"},
    "Organization > Policy objects": {"org_policy_objects", "org_policy_object_groups"},
}

_PER_SSID_SUBAREAS: set[str] = {
    "wireless_ssid_l3_firewall",
    "wireless_ssid_l7_firewall",
    "wireless_ssid_traffic_shaping",
    "wireless_ssid_splash",
    "wireless_ssid_schedules",
    "wireless_ssid_vpn",
    "wireless_ssid_device_type_policies",
    "wireless_ssid_identity_psks",
}


def event_to_endpoints(event: dict) -> set[str]:
    """Map a Meraki change-log event to the set of config_areas to re-pull.

    Uses the event's `page` string as the primary key. If the event references
    a specific SSID (ssidNumber set), expands to include per-SSID sub-endpoints
    even if the change was only to an SSID-level setting — the reactive catch
    required by the spec.

    Returns an empty set for events with no known mapping; callers log these.
    """
    page = event.get("page") or ""
    areas: set[str] = set()
    for prefix, mapped in _PAGE_PREFIX_MAP.items():
        if page.startswith(prefix):
            areas |= mapped
            break

    # Reactive catch: any event with ssidNumber triggers per-SSID pulls
    if event.get("ssidNumber") is not None:
        areas |= {"wireless_ssids"} | _PER_SSID_SUBAREAS

    return areas
