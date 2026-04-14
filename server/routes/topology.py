"""Topology API routes.

Provides L2 (physical) and L3 (logical) topology views,
including device drill-down and VLAN member queries.
"""

from fastapi import APIRouter, HTTPException, Request

from server.models import L2Topology, L3Topology

router = APIRouter(prefix="/api/topology", tags=["topology"])


# --------------------------------------------------------------------------- #
# L2 Physical Topology
# --------------------------------------------------------------------------- #


@router.get("/l2", response_model=L2Topology)
async def get_l2_topology(request: Request):
    """Return the full L2 physical topology (nodes + edges)."""
    poller = request.state.poller
    if poller is None or poller.l2_topology is None:
        raise HTTPException(status_code=503, detail="Topology not yet available")
    return poller.l2_topology


@router.get("/l2/device/{device_id}")
async def get_l2_device_detail(device_id: str, request: Request):
    """Device drill-down: return the device and its directly connected children/edges."""
    poller = request.state.poller
    if poller is None or poller.l2_topology is None:
        raise HTTPException(status_code=503, detail="Topology not yet available")

    l2 = poller.l2_topology

    # Find the device
    device = next((n for n in l2.nodes if n.id == device_id), None)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")

    # Edges where this device is source or target
    connected_edges = [
        e for e in l2.edges if e.source == device_id or e.target == device_id
    ]

    # Neighbour device IDs
    neighbour_ids = set()
    for e in connected_edges:
        neighbour_ids.add(e.source if e.source != device_id else e.target)

    # Neighbour device objects
    neighbours = [n for n in l2.nodes if n.id in neighbour_ids]

    return {
        "device": device.model_dump(),
        "neighbours": [n.model_dump() for n in neighbours],
        "edges": [e.model_dump() for e in connected_edges],
    }


# --------------------------------------------------------------------------- #
# L3 Logical Topology
# --------------------------------------------------------------------------- #


@router.get("/l3", response_model=L3Topology)
async def get_l3_topology(request: Request):
    """Return the full L3 logical topology (subnets + routes)."""
    poller = request.state.poller
    if poller is None or poller.l3_topology is None:
        raise HTTPException(status_code=503, detail="Topology not yet available")
    return poller.l3_topology


@router.get("/l3/vlan/{vlan_id}")
async def get_vlan_members(vlan_id: int, request: Request):
    """Return all devices belonging to a specific VLAN."""
    poller = request.state.poller
    if poller is None or poller.l2_topology is None:
        raise HTTPException(status_code=503, detail="Topology not yet available")

    l2 = poller.l2_topology
    l3 = poller.l3_topology

    # Find the subnet entry
    subnet = None
    if l3:
        subnet = next((s for s in l3.subnets if s.vlan == vlan_id), None)

    if subnet is None:
        raise HTTPException(status_code=404, detail=f"VLAN {vlan_id} not found")

    # Devices whose vlan field matches, or whose interfaces include this VLAN
    members = [
        n
        for n in l2.nodes
        if n.vlan == vlan_id
        or any(iface.vlan == vlan_id for iface in n.interfaces)
    ]

    return {
        "subnet": subnet.model_dump(),
        "devices": [d.model_dump() for d in members],
    }
