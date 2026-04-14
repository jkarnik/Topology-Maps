"""Device API routes.

Provides device listing, detail, and interface information.
"""

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("")
async def list_devices(request: Request):
    """List all devices with their current status."""
    poller = request.state.poller
    if poller is None or poller.l2_topology is None:
        raise HTTPException(status_code=503, detail="Topology not yet available")

    devices = poller.l2_topology.nodes
    return {
        "devices": [
            {
                "id": d.id,
                "type": d.type,
                "model": d.model,
                "ip": d.ip,
                "status": d.status,
                "floor": d.floor,
                "category": d.category,
            }
            for d in devices
        ],
        "count": len(devices),
    }


@router.get("/{device_id}")
async def get_device(device_id: str, request: Request):
    """Get full detail for a single device."""
    poller = request.state.poller
    if poller is None or poller.l2_topology is None:
        raise HTTPException(status_code=503, detail="Topology not yet available")

    device = next(
        (n for n in poller.l2_topology.nodes if n.id == device_id), None
    )
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")

    return device.model_dump()


@router.get("/{device_id}/interfaces")
async def get_device_interfaces(device_id: str, request: Request):
    """List interfaces and their stats for a device."""
    poller = request.state.poller
    if poller is None or poller.l2_topology is None:
        raise HTTPException(status_code=503, detail="Topology not yet available")

    device = next(
        (n for n in poller.l2_topology.nodes if n.id == device_id), None
    )
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")

    return {
        "device_id": device_id,
        "interfaces": [iface.model_dump() for iface in device.interfaces],
        "count": len(device.interfaces),
    }
