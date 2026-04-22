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
            await self._limiter.acquire()
            resp = await self._client.get(next_url)
            resp.raise_for_status()
            results.extend(resp.json())
            page_count += 1
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

    async def close(self) -> None:
        await self._client.aclose()
