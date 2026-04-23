import logging
import os
from typing import Optional, Union
import httpx
from server.rate_limiter import RateLimiter
import re as _re

logger = logging.getLogger(__name__)
MERAKI_BASE_URL = "https://api.meraki.com/api/v1"


class MaxPagesExceeded(Exception):
    """Raised when paginated fetch exceeds the configured page ceiling."""


_LINK_NEXT_RE = _re.compile(r'<([^>]+)>;\s*rel="next"')


def _parse_link_header(header):
    """Return the URL of the rel=next link, or None if absent."""
    if not header:
        return None
    m = _LINK_NEXT_RE.search(header)
    return m.group(1) if m else None


class MerakiClient:
    def __init__(self, api_key: Optional[str] = None, rate_limit: float = 5.0):
        self.api_key = api_key or os.environ.get("MERAKI_API_KEY", "")
        self._limiter = RateLimiter(rate=rate_limit, capacity=int(rate_limit))
        self._client = httpx.AsyncClient(
            base_url=MERAKI_BASE_URL,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            timeout=30.0,
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def _get(self, path: str, params: Optional[dict] = None) -> Union[dict, list]:
        await self._limiter.acquire()
        logger.debug("Meraki API GET %s", path)
        resp = await self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def _get_paginated(
        self,
        path: str,
        params: Optional[dict] = None,
        per_page: int = 1000,
        max_pages: int = 100,
    ) -> list:
        """Fetch `path` with RFC 5988 Link-header pagination, concatenating items.

        Each page fetch passes through the rate limiter. Raises
        `MaxPagesExceeded` if more than `max_pages` pages would be fetched.
        """
        merged_params = {"perPage": per_page, **(params or {})}
        await self._limiter.acquire()
        resp = await self._client.get(path, params=merged_params)
        resp.raise_for_status()
        results = list(resp.json())

        page_count = 1
        next_url = _parse_link_header(resp.headers.get("Link"))
        while next_url:
            if page_count >= max_pages:
                raise MaxPagesExceeded(f"exceeded max_pages={max_pages} for {path}")
            page_count += 1
            await self._limiter.acquire()
            resp = await self._client.get(next_url)
            resp.raise_for_status()
            results.extend(resp.json())
            next_url = _parse_link_header(resp.headers.get("Link"))

        return results

    async def get_organizations(self) -> list[dict]:
        return await self._get("/organizations")

    async def get_org_devices(self, org_id: str) -> list[dict]:
        return await self._get(f"/organizations/{org_id}/devices")

    async def get_org_device_availabilities(self, org_id: str) -> list[dict]:
        """Replaces the deprecated /devices/statuses `status` field.

        Returns a list of {serial, status, productType, network, ...} with
        status in {online, alerting, offline, dormant}.
        """
        return await self._get(f"/organizations/{org_id}/devices/availabilities")

    async def get_org_device_uplinks_addresses(self, org_id: str) -> list[dict]:
        """Replaces the deprecated /devices/statuses network fields.

        Returns a list of {serial, network, uplinks: [{interface, addresses: [...]}]}
        with public IP, gateway, DNS, and assignment mode per uplink.
        """
        return await self._get(
            f"/organizations/{org_id}/devices/uplinks/addresses/byDevice"
        )

    async def get_org_networks(self, org_id: str) -> list[dict]:
        return await self._get(f"/organizations/{org_id}/networks")

    async def get_network_topology(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/topology/linkLayer")

    async def get_network_vlans(self, network_id: str) -> list[dict]:
        try:
            return await self._get(f"/networks/{network_id}/appliance/vlans")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                return []
            raise

    async def get_network_ssids(self, network_id: str) -> list[dict]:
        try:
            return await self._get(f"/networks/{network_id}/wireless/ssids")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                return []
            raise

    async def get_device_clients(self, serial: str, timespan: int = 300) -> list[dict]:
        return await self._get(f"/devices/{serial}/clients", params={"timespan": timespan})

    async def get_device_switch_ports(self, serial: str) -> list[dict]:
        try:
            return await self._get(f"/devices/{serial}/switch/ports/statuses")
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (400, 404):
                return []
            raise

    async def get_network_switch_stacks(self, network_id: str) -> list[dict]:
        try:
            return await self._get(f"/networks/{network_id}/switch/stacks")
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (400, 404):
                return []
            raise

    # --- Plan 1.06: Organization-level endpoints (access/policy) -----------

    async def get_org_admins(self, org_id: str) -> list[dict]:
        return await self._get(f"/organizations/{org_id}/admins")

    async def get_org_saml_roles(self, org_id: str) -> list[dict]:
        return await self._get(f"/organizations/{org_id}/samlRoles")

    async def get_org_saml(self, org_id: str) -> dict:
        return await self._get(f"/organizations/{org_id}/saml")

    async def get_org_login_security(self, org_id: str) -> dict:
        return await self._get(f"/organizations/{org_id}/loginSecurity")

    async def get_org_policy_objects(self, org_id: str) -> list[dict]:
        return await self._get_paginated(f"/organizations/{org_id}/policyObjects")

    async def get_org_policy_object_groups(self, org_id: str) -> list[dict]:
        return await self._get_paginated(f"/organizations/{org_id}/policyObjects/groups")

    async def get_org_config_templates(self, org_id: str) -> list[dict]:
        return await self._get(f"/organizations/{org_id}/configTemplates")

    async def get_org_adaptive_policy_settings(self, org_id: str) -> dict:
        return await self._get(f"/organizations/{org_id}/adaptivePolicy/settings")

    async def get_org_adaptive_policy_acls(self, org_id: str) -> list[dict]:
        return await self._get(f"/organizations/{org_id}/adaptivePolicy/acls")

    async def get_org_adaptive_policy_groups(self, org_id: str) -> list[dict]:
        return await self._get(f"/organizations/{org_id}/adaptivePolicy/groups")

    async def get_org_adaptive_policy_policies(self, org_id: str) -> list[dict]:
        return await self._get(f"/organizations/{org_id}/adaptivePolicy/policies")

    async def get_org_appliance_vpn_third_party_peers(self, org_id: str) -> dict:
        return await self._get(f"/organizations/{org_id}/appliance/vpn/thirdPartyVPNPeers")

    async def get_org_appliance_vpn_firewall(self, org_id: str) -> dict:
        return await self._get(f"/organizations/{org_id}/appliance/vpn/vpnFirewallRules")

    async def get_org_snmp(self, org_id: str) -> dict:
        return await self._get(f"/organizations/{org_id}/snmp")

    async def get_org_alerts_profiles(self, org_id: str) -> list[dict]:
        return await self._get(f"/organizations/{org_id}/alerts/profiles")

    async def get_org_inventory_devices(self, org_id: str) -> list[dict]:
        return await self._get_paginated(f"/organizations/{org_id}/inventory/devices")

    async def get_org_licenses_per_device(self, org_id: str) -> list[dict]:
        return await self._get_paginated(f"/organizations/{org_id}/licenses")

    async def get_org_licenses_coterm(self, org_id: str) -> list[dict]:
        return await self._get_paginated(f"/organizations/{org_id}/licensing/coterm/licenses")

    # --- Plan 1.07: Network-generic endpoints ----------------------------

    async def get_network_metadata(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}")

    async def get_network_settings(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/settings")

    async def get_network_group_policies(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/groupPolicies")

    async def get_network_syslog_servers(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/syslogServers")

    async def get_network_snmp(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/snmp")

    async def get_network_traffic_analysis(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/trafficAnalysis")

    async def get_network_netflow(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/netflow")

    async def get_network_alerts_settings(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/alerts/settings")

    async def get_network_webhooks_http_servers(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/webhooks/httpServers")

    async def get_network_webhooks_payload_templates(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/webhooks/payloadTemplates")

    async def get_network_firmware_upgrades(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/firmwareUpgrades")

    async def get_network_floor_plans(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/floorPlans")

    # --- Plan 1.07: MX appliance (VLAN / ports / firewall) -----------------

    async def get_appliance_vlans(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/appliance/vlans")

    async def get_appliance_vlans_settings(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/vlans/settings")

    async def get_appliance_single_lan(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/singleLan")

    async def get_appliance_ports(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/appliance/ports")

    async def get_appliance_firewall_l3(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/firewall/l3FirewallRules")

    async def get_appliance_firewall_l7(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/firewall/l7FirewallRules")

    async def get_appliance_firewall_inbound(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/firewall/inboundFirewallRules")

    async def get_appliance_firewall_port_forwarding(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/firewall/portForwardingRules")

    async def get_appliance_firewall_one_to_one_nat(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/firewall/oneToOneNatRules")

    async def get_appliance_firewall_one_to_many_nat(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/firewall/oneToManyNatRules")

    async def get_appliance_firewall_firewalled_services(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/appliance/firewall/firewalledServices")

    async def get_appliance_firewall_settings(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/firewall/settings")

    async def get_appliance_firewall_cellular(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/firewall/cellularFirewallRules")

    # --- Plan 1.07: MX security / shaping / VPN / routing ------------------

    async def get_appliance_content_filtering(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/contentFiltering")

    async def get_appliance_security_intrusion(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/security/intrusion")

    async def get_appliance_security_malware(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/security/malware")

    async def get_appliance_traffic_shaping_rules(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/trafficShaping/rules")

    async def get_appliance_uplink_bandwidth(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/trafficShaping/uplinkBandwidth")

    async def get_appliance_uplink_selection(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/trafficShaping/uplinkSelection")

    async def get_appliance_custom_performance_classes(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/appliance/trafficShaping/customPerformanceClasses")

    async def get_appliance_site_to_site_vpn(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/vpn/siteToSiteVpn")

    async def get_appliance_vpn_bgp(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/vpn/bgp")

    async def get_appliance_static_routes(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/appliance/staticRoutes")

    async def get_appliance_warm_spare(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/warmSpare")

    async def get_appliance_connectivity_monitoring(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/connectivityMonitoringDestinations")

    async def get_appliance_settings(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/settings")

    # --- Plan 1.08: MS switch ---------------------------------------------

    async def get_switch_access_policies(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/switch/accessPolicies")

    async def get_switch_acls(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/switch/accessControlLists")

    async def get_switch_qos_rules(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/switch/qosRules")

    async def get_switch_qos_order(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/switch/qosRules/order")

    async def get_switch_dscp_to_cos(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/switch/dscpToCosMappings")

    async def get_switch_settings(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/switch/settings")

    async def get_switch_stp(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/switch/stp")

    async def get_switch_storm_control(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/switch/stormControl")

    async def get_switch_mtu(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/switch/mtu")

    async def get_switch_stacks(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/switch/stacks")

    async def get_switch_port_schedules(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/switch/portSchedules")

    async def get_switch_link_aggregations(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/switch/linkAggregations")

    async def get_switch_dhcp_server_policy(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/switch/dhcpServerPolicy")

    async def get_switch_multicast(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/switch/routing/multicast")

    async def get_switch_multicast_rps(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/switch/routing/multicast/rendezvousPoints")

    async def get_switch_ospf(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/switch/routing/ospf")

    # --- Plan 1.08: MR wireless (network-level) --------------------------

    async def get_wireless_ssids(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/wireless/ssids")

    async def get_wireless_rf_profiles(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/wireless/rfProfiles")

    async def get_wireless_settings(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/wireless/settings")

    async def get_wireless_bluetooth(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/wireless/bluetooth/settings")

    async def get_wireless_ap_port_profiles(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/wireless/ethernet/ports/profiles")

    # --- Plan 1.08: Per-SSID sub-endpoints --------------------------------

    async def get_wireless_ssid_l3_firewall(self, network_id: str, ssid_number: int) -> dict:
        return await self._get(f"/networks/{network_id}/wireless/ssids/{ssid_number}/firewall/l3FirewallRules")

    async def get_wireless_ssid_l7_firewall(self, network_id: str, ssid_number: int) -> dict:
        return await self._get(f"/networks/{network_id}/wireless/ssids/{ssid_number}/firewall/l7FirewallRules")

    async def get_wireless_ssid_traffic_shaping(self, network_id: str, ssid_number: int) -> dict:
        return await self._get(f"/networks/{network_id}/wireless/ssids/{ssid_number}/trafficShaping/rules")

    async def get_wireless_ssid_splash(self, network_id: str, ssid_number: int) -> dict:
        return await self._get(f"/networks/{network_id}/wireless/ssids/{ssid_number}/splash/settings")

    async def get_wireless_ssid_schedules(self, network_id: str, ssid_number: int) -> dict:
        return await self._get(f"/networks/{network_id}/wireless/ssids/{ssid_number}/schedules")

    async def get_wireless_ssid_vpn(self, network_id: str, ssid_number: int) -> dict:
        return await self._get(f"/networks/{network_id}/wireless/ssids/{ssid_number}/vpn")

    async def get_wireless_ssid_device_type_policies(self, network_id: str, ssid_number: int) -> dict:
        return await self._get(f"/networks/{network_id}/wireless/ssids/{ssid_number}/deviceTypeGroupPolicies")

    async def get_wireless_ssid_identity_psks(self, network_id: str, ssid_number: int) -> list[dict]:
        return await self._get(f"/networks/{network_id}/wireless/ssids/{ssid_number}/identityPsks")

    # --- Plan 1.09: Device metadata + mgmt interface ----------------------

    async def get_device_metadata(self, serial: str) -> dict:
        return await self._get(f"/devices/{serial}")

    async def get_device_management_interface(self, serial: str) -> dict:
        return await self._get(f"/devices/{serial}/managementInterface")

    async def close(self) -> None:
        await self._client.aclose()
