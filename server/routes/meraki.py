"""Meraki Dashboard API proxy routes with SSE progressive refresh.

Provides:
  GET  /api/meraki/status                      — validate API key, return org info
  GET  /api/meraki/networks                    — list networks for the first org
  GET  /api/meraki/topology/l2?network={id}    — L2 topology for a network
  GET  /api/meraki/topology/l3?network={id}    — L3 topology for a network
  GET  /api/meraki/devices/{serial}            — device detail + clients
  POST /api/meraki/refresh?network={id}        — SSE progressive refresh
"""

import asyncio
import json
import logging
import time
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from server.meraki_client import MerakiClient
from server.meraki_transformer import MerakiTransformer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meraki", tags=["meraki"])

# ---------------------------------------------------------------------------
# Shared state — lazy-initialised on first request
# ---------------------------------------------------------------------------

_client: Optional[MerakiClient] = None
_org_id: Optional[str] = None
_transformer = MerakiTransformer()


def _get_client() -> MerakiClient:
    """Return the shared MerakiClient, creating it on first call."""
    global _client
    if _client is None:
        _client = MerakiClient()
    return _client


async def _get_org_id() -> str:
    """Return the cached org ID, fetching it from the API if needed."""
    global _org_id
    if _org_id is not None:
        return _org_id

    client = _get_client()
    if not client.is_configured:
        raise HTTPException(status_code=401, detail="MERAKI_API_KEY not configured")

    try:
        orgs = await client.get_organizations()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"Meraki API error: {exc.response.text}",
        ) from exc

    if not orgs:
        raise HTTPException(status_code=404, detail="No Meraki organizations found")

    _org_id = orgs[0]["id"]
    return _org_id


# ---------------------------------------------------------------------------
# GET /api/meraki/status
# ---------------------------------------------------------------------------


@router.get("/status")
async def get_status():
    """Validate the API key and return basic org info."""
    client = _get_client()
    if not client.is_configured:
        raise HTTPException(status_code=401, detail="MERAKI_API_KEY not configured")

    try:
        orgs = await client.get_organizations()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"Meraki API error: {exc.response.text}",
        ) from exc

    return {
        "configured": True,
        "organization_count": len(orgs),
        "organizations": [
            {"id": o.get("id"), "name": o.get("name")} for o in orgs
        ],
    }


# ---------------------------------------------------------------------------
# GET /api/meraki/networks
# ---------------------------------------------------------------------------


@router.get("/networks")
async def get_networks():
    """List all networks for the first organisation."""
    org_id = await _get_org_id()
    client = _get_client()

    try:
        networks = await client.get_org_networks(org_id)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"Meraki API error: {exc.response.text}",
        ) from exc

    return {"networks": networks}


# ---------------------------------------------------------------------------
# GET /api/meraki/topology/l2
# ---------------------------------------------------------------------------


@router.get("/topology/l2")
async def get_l2_topology(network: Optional[str] = Query(None, description="Network ID")):
    """Return L2 topology for a specific network."""
    org_id = await _get_org_id()
    client = _get_client()

    try:
        devices, statuses = await asyncio.gather(
            client.get_org_devices(org_id),
            client.get_org_device_statuses(org_id),
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"Meraki API error: {exc.response.text}",
        ) from exc

    # Filter devices to network if specified
    if network:
        devices = [d for d in devices if d.get("networkId") == network]
        network_ids = [network]
    else:
        network_ids = list({d.get("networkId") for d in devices if d.get("networkId")})

    # Fetch link-layer topology per network
    all_link_layer = []
    for nid in network_ids:
        try:
            ll = await client.get_network_topology(nid)
            all_link_layer.append(ll)
        except Exception:
            logger.warning("Failed to get link-layer for network %s", nid)

    # Fetch clients for APs to show wireless connections
    ap_serials = [d["serial"] for d in devices if d.get("productType") == "wireless" and d.get("serial")]
    clients_by_ap: dict[str, list[dict]] = {}
    for serial in ap_serials:
        try:
            clients = await client.get_device_clients(serial)
            if clients:
                clients_by_ap[serial] = clients
        except Exception:
            pass

    l2 = _transformer.build_l2(devices, statuses, all_link_layer, clients_by_ap)
    return l2.model_dump()


# ---------------------------------------------------------------------------
# GET /api/meraki/topology/l3
# ---------------------------------------------------------------------------


@router.get("/topology/l3")
async def get_l3_topology(network: Optional[str] = Query(None, description="Network ID")):
    """Return L3 topology for a specific network."""
    org_id = await _get_org_id()
    client = _get_client()

    try:
        devices = await client.get_org_devices(org_id)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"Meraki API error: {exc.response.text}",
        ) from exc

    if network:
        devices = [d for d in devices if d.get("networkId") == network]
        network_ids = [network]
    else:
        network_ids = list({d.get("networkId") for d in devices if d.get("networkId")})

    vlans_by_network = {}
    for nid in network_ids:
        try:
            vlans = await client.get_network_vlans(nid)
            if vlans:
                vlans_by_network[nid] = vlans
        except Exception:
            logger.warning("Failed to get VLANs for network %s", nid)

    l3 = _transformer.build_l3(vlans_by_network, devices)
    return l3.model_dump()


# ---------------------------------------------------------------------------
# GET /api/meraki/devices/{serial}
# ---------------------------------------------------------------------------


@router.get("/devices/{serial}")
async def get_device_detail(serial: str):
    """Return device detail and recent clients for a given serial number."""
    client = _get_client()
    if not client.is_configured:
        raise HTTPException(status_code=401, detail="MERAKI_API_KEY not configured")

    try:
        clients, ports = await asyncio.gather(
            client.get_device_clients(serial),
            client.get_device_switch_ports(serial),
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"Meraki API error: {exc.response.text}",
        ) from exc

    return {
        "serial": serial,
        "clients": clients,
        "switch_ports": ports,
    }


# ---------------------------------------------------------------------------
# POST /api/meraki/refresh  (SSE)
# ---------------------------------------------------------------------------


@router.post("/refresh")
async def refresh_topology(network: Optional[str] = Query(None, description="Network ID")):
    """Stream a progressive topology refresh over Server-Sent Events.

    Phases emitted:
      1. discovery  — org-level device + network counts with time estimate
      2. topology   — per-network L2 topology (nodes + edges)
      3. clients    — per-device client counts
      4. complete   — final L2 + L3 topology payloads
    """
    org_id = await _get_org_id()
    client = _get_client()

    async def event_generator():
        start = time.monotonic()

        # ------------------------------------------------------------------ #
        # Phase 1: discovery
        # ------------------------------------------------------------------ #
        try:
            devices, networks_list, statuses = await asyncio.gather(
                client.get_org_devices(org_id),
                client.get_org_networks(org_id),
                client.get_org_device_statuses(org_id),
            )
        except httpx.HTTPStatusError as exc:
            yield {
                "event": "error",
                "data": json.dumps({"detail": f"Meraki API error: {exc.response.text}"}),
            }
            return

        device_count = len(devices)
        network_count = len(networks_list)
        # Rough estimate: ~2 s per network for topology + client calls
        estimated_seconds = network_count * 2

        yield {
            "event": "message",
            "data": json.dumps({
                "phase": "discovery",
                "device_count": device_count,
                "network_count": network_count,
                "estimated_seconds": estimated_seconds,
            }),
        }

        # Narrow to the requested network, or use all
        if network:
            target_networks = [n for n in networks_list if n.get("id") == network]
            if not target_networks:
                target_networks = networks_list
        else:
            target_networks = networks_list

        # ------------------------------------------------------------------ #
        # Phase 2: topology (per network)
        # ------------------------------------------------------------------ #
        all_link_layer: list[dict] = []
        vlans_by_network: dict[str, list[dict]] = {}
        total = len(target_networks)

        for idx, net in enumerate(target_networks, start=1):
            net_id = net.get("id", "")
            elapsed = time.monotonic() - start
            remaining = max(0.0, estimated_seconds - elapsed)

            try:
                link_layer, vlans = await asyncio.gather(
                    client.get_network_topology(net_id),
                    client.get_network_vlans(net_id),
                )
            except httpx.HTTPStatusError:
                link_layer = {}
                vlans = []

            all_link_layer.append(link_layer)
            vlans_by_network[net_id] = vlans

            # Build partial L2 for this network to stream nodes/edges
            net_devices = [d for d in devices if d.get("networkId") == net_id]
            partial_l2 = _transformer.build_l2(net_devices, statuses, [link_layer])

            yield {
                "event": "message",
                "data": json.dumps({
                    "phase": "topology",
                    "network": net_id,
                    "nodes": [n.model_dump() for n in partial_l2.nodes],
                    "edges": [e.model_dump() for e in partial_l2.edges],
                    "progress": idx,
                    "total": total,
                    "remaining_seconds": round(remaining, 1),
                }),
            }

        # ------------------------------------------------------------------ #
        # Phase 3: clients
        # ------------------------------------------------------------------ #
        target_network_ids = {n.get("id") for n in target_networks}
        net_devices_flat = [d for d in devices if d.get("networkId") in target_network_ids]
        client_counts: dict[str, int] = {}

        for dev in net_devices_flat:
            serial = dev.get("serial", "")
            if not serial:
                continue
            elapsed = time.monotonic() - start
            remaining = max(0.0, estimated_seconds - elapsed)

            try:
                dev_clients = await client.get_device_clients(serial)
                client_counts[serial] = len(dev_clients)
            except httpx.HTTPStatusError:
                client_counts[serial] = 0

        yield {
            "event": "message",
            "data": json.dumps({
                "phase": "clients",
                "client_counts": client_counts,
                "remaining_seconds": round(max(0.0, estimated_seconds - (time.monotonic() - start)), 1),
            }),
        }

        # ------------------------------------------------------------------ #
        # Phase 4: complete — full L2 + L3
        # ------------------------------------------------------------------ #
        final_devices = [d for d in devices if d.get("networkId") in target_network_ids]
        final_l2 = _transformer.build_l2(final_devices, statuses, all_link_layer)
        final_l3 = _transformer.build_l3(vlans_by_network, final_devices)

        yield {
            "event": "message",
            "data": json.dumps({
                "phase": "complete",
                "l2": final_l2.model_dump(),
                "l3": final_l3.model_dump(),
            }),
        }

    return EventSourceResponse(event_generator())
