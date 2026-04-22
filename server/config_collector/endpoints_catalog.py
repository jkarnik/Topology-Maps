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
