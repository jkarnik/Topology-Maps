"""Simulator internal REST API.

Provides an aiohttp web server that the FastAPI server uses to push
connection changes (create, move, delete) into the running simulator.
Runs alongside the SNMP agents on SIMULATOR_REST_PORT (8001).
"""

from __future__ import annotations

import logging
from aiohttp import web

from simulator.topology_state import TopologyState

logger = logging.getLogger(__name__)


class SimulatorAPI:
    """REST API for mutating the simulator's topology state."""

    def __init__(self, topology_state: TopologyState, agent_count: int = 7):
        self._state = topology_state
        self._agent_count = agent_count
        self._app = web.Application()
        self._runner: web.AppRunner | None = None
        self._setup_routes()

    def _setup_routes(self) -> None:
        self._app.router.add_post("/simulator/connections", self._handle_connection)
        self._app.router.add_get("/health", self._handle_health)
        self._app.router.add_get("/simulator/state", self._handle_state)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, port: int) -> None:
        """Start the REST API server on the given port."""
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", port)
        await site.start()
        logger.info("Simulator REST API started on port %d", port)

    async def stop(self) -> None:
        """Gracefully shut down the REST API server."""
        if self._runner:
            await self._runner.cleanup()
            logger.info("Simulator REST API stopped")

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_health(self, request: web.Request) -> web.Response:
        """GET /health -- simple liveness check."""
        return web.json_response({
            "status": "healthy",
            "agents": self._agent_count,
        })

    async def _handle_state(self, request: web.Request) -> web.Response:
        """GET /simulator/state -- topology state summary for debugging."""
        state = self._state
        return web.json_response({
            "devices": len(state.devices),
            "aps": len(state.aps),
            "wireless_clients": len(state.wireless_clients),
            "version": state.version,
        })

    async def _handle_connection(self, request: web.Request) -> web.Response:
        """POST /simulator/connections -- create, move, or delete a connection."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response(
                {"status": "error", "message": "Invalid JSON body"},
                status=400,
            )

        action = body.get("action")
        device = body.get("device")

        if not action or not device:
            return web.json_response(
                {"status": "error", "message": "Missing required fields: action, device"},
                status=400,
            )

        if action == "move":
            return await self._action_move(body, device)
        elif action == "create":
            return await self._action_create(body, device)
        elif action == "delete":
            return await self._action_delete(body, device)
        else:
            return web.json_response(
                {"status": "error", "message": f"Unknown action: {action}"},
                status=400,
            )

    # ------------------------------------------------------------------
    # Action helpers
    # ------------------------------------------------------------------

    async def _action_move(self, body: dict, device: str) -> web.Response:
        """Move a device from one switch/port to another."""
        from_info = body.get("from")
        to_info = body.get("to")

        if not from_info or not to_info:
            return web.json_response(
                {"status": "error", "message": "Move requires 'from' and 'to' fields"},
                status=400,
            )

        from_switch = from_info.get("switch")
        from_port = from_info.get("port")
        to_switch = to_info.get("switch")
        to_port = to_info.get("port")

        if not all([from_switch, from_port is not None, to_switch, to_port is not None]):
            return web.json_response(
                {"status": "error", "message": "from/to must include 'switch' and 'port'"},
                status=400,
            )

        ok = self._state.move_connection(
            device_id=device,
            from_switch=from_switch,
            from_port=int(from_port),
            to_switch=to_switch,
            to_port=int(to_port),
        )

        if ok:
            logger.info(
                "Moved %s from %s:%s to %s:%s",
                device, from_switch, from_port, to_switch, to_port,
            )
            return web.json_response({"status": "ok", "message": "Connection updated"})
        else:
            return web.json_response(
                {"status": "error", "message": f"Move failed -- device or switch not found"},
                status=404,
            )

    async def _action_create(self, body: dict, device: str) -> web.Response:
        """Create a new connection (move with from=null)."""
        to_info = body.get("to")
        if not to_info:
            return web.json_response(
                {"status": "error", "message": "Create requires 'to' field"},
                status=400,
            )

        to_switch = to_info.get("switch")
        to_port = to_info.get("port")

        if not to_switch or to_port is None:
            return web.json_response(
                {"status": "error", "message": "'to' must include 'switch' and 'port'"},
                status=400,
            )

        # For create, we add LLDP/ARP/MAC entries on the destination switch
        dst_switch = self._state.get_device(to_switch)
        if not dst_switch:
            return web.json_response(
                {"status": "error", "message": f"Switch '{to_switch}' not found"},
                status=404,
            )

        # Resolve device name and IP
        from simulator.topology_state import LLDPNeighbor

        ap = self._state.get_ap(device)
        if ap:
            device_name = ap.name
            device_ip = ap.ip
        else:
            dev = self._state.get_device(device)
            if dev:
                device_name = device
                device_ip = dev.ip
            else:
                return web.json_response(
                    {"status": "error", "message": f"Device '{device}' not found"},
                    status=404,
                )

        dst_port_name = f"port{int(to_port)}"

        # Add LLDP neighbor on the destination switch
        dst_switch.lldp_neighbors.append(
            LLDPNeighbor(
                local_port=dst_port_name,
                remote_device_id=device,
                remote_port="eth0",
                remote_device_name=device_name,
                remote_ip=device_ip,
            )
        )

        # Update AP parent if applicable
        if ap:
            ap.parent_switch = to_switch
            ap.parent_port = dst_port_name

        self._state._version += 1

        logger.info("Created connection: %s on %s:%s", device, to_switch, to_port)
        return web.json_response({"status": "ok", "message": "Connection created"})

    async def _action_delete(self, body: dict, device: str) -> web.Response:
        """Delete a connection (remove LLDP/ARP/MAC entries)."""
        from_info = body.get("from")
        if not from_info:
            return web.json_response(
                {"status": "error", "message": "Delete requires 'from' field"},
                status=400,
            )

        from_switch = from_info.get("switch")
        from_port = from_info.get("port")

        if not from_switch or from_port is None:
            return web.json_response(
                {"status": "error", "message": "'from' must include 'switch' and 'port'"},
                status=400,
            )

        src_switch = self._state.get_device(from_switch)
        if not src_switch:
            return web.json_response(
                {"status": "error", "message": f"Switch '{from_switch}' not found"},
                status=404,
            )

        src_port_name = f"port{int(from_port)}"

        # Remove LLDP neighbor entries for this device on this port
        src_switch.lldp_neighbors = [
            n for n in src_switch.lldp_neighbors
            if not (n.local_port == src_port_name and n.remote_device_id == device)
        ]

        # Remove ARP entries on this port
        src_switch.arp_table = [
            e for e in src_switch.arp_table
            if e.port != src_port_name
        ]

        # Remove MAC entries on this port
        src_switch.mac_table = [
            e for e in src_switch.mac_table
            if e.port != src_port_name
        ]

        # Clear AP parent if applicable
        ap = self._state.get_ap(device)
        if ap and ap.parent_switch == from_switch:
            ap.parent_switch = ""
            ap.parent_port = ""

        self._state._version += 1

        logger.info("Deleted connection: %s from %s:%s", device, from_switch, from_port)
        return web.json_response({"status": "ok", "message": "Connection deleted"})
