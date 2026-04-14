"""SNMP v2c agent that serves an in-memory MIB tree over UDP.

Each simulated network device gets its own :class:`SNMPAgent` instance
listening on a unique ``localhost`` UDP port. The agent handles
**GetRequest**, **GetNextRequest**, and **GetBulkRequest** PDUs from
any standard SNMP client (pysnmp, ``snmpwalk``, ``snmpget``, etc.).

The MIB tree is a sorted list of ``(oid_tuple, pysnmp_value)`` pairs
and can be hot-swapped at runtime via :meth:`SNMPAgent.update_mib_tree`
(e.g. when roaming or connection edits change the topology state).
"""

from __future__ import annotations

import asyncio
import bisect
import logging
import threading
from typing import Optional

from pyasn1.codec.ber import decoder, encoder
from pysnmp.proto.api import v2c
from pysnmp.proto.rfc1905 import EndOfMibView, NoSuchInstance, NoSuchObject

logger = logging.getLogger(__name__)

# Sentinel values used in SNMP v2c responses
_END_OF_MIB_VIEW = EndOfMibView("")
_NO_SUCH_INSTANCE = NoSuchInstance("")
_NO_SUCH_OBJECT = NoSuchObject("")

# Pre-computed tag sets for PDU type identification
_TAG_GET = v2c.GetRequestPDU.tagSet
_TAG_GETNEXT = v2c.GetNextRequestPDU.tagSet
_TAG_GETBULK = v2c.GetBulkRequestPDU.tagSet


class SNMPAgent:
    """An asyncio-based SNMP v2c agent serving an in-memory MIB tree.

    Parameters
    ----------
    device_id : str
        Unique identifier for this simulated device (used for logging).
    port : int
        UDP port to listen on (``127.0.0.1``).
    mib_tree : list[tuple]
        Sorted list of ``(oid_tuple, pysnmp_value)`` pairs.  Must be
        sorted by OID for correct GETNEXT/WALK behaviour.  Use
        :func:`simulator.devices.base.sort_mib_tree` to guarantee order.
    community : str
        SNMP community string (default ``"public"``).
    bind_address : str
        IP address to bind the UDP socket to (default ``"127.0.0.1"``).
    """

    def __init__(
        self,
        device_id: str,
        port: int,
        mib_tree: list[tuple],
        community: str = "public",
        bind_address: str = "0.0.0.0",
    ) -> None:
        self.device_id = device_id
        self.port = port
        self.community = community
        self.bind_address = bind_address

        # The MIB tree and its OID-only index for fast binary search.
        # Protected by a lock so update_mib_tree is safe from any thread.
        self._lock = threading.Lock()
        self._mib_tree: list[tuple] = list(mib_tree)
        self._oid_keys: list[tuple] = [entry[0] for entry in self._mib_tree]

        # asyncio transport/protocol references (set by start())
        self._transport: Optional[asyncio.DatagramTransport] = None
        self._protocol: Optional[_SNMPProtocol] = None

    # ------------------------------------------------------------------
    # MIB tree management
    # ------------------------------------------------------------------

    def update_mib_tree(self, new_tree: list[tuple]) -> None:
        """Replace the MIB tree atomically (thread-safe).

        *new_tree* must already be sorted by OID.
        """
        with self._lock:
            self._mib_tree = list(new_tree)
            self._oid_keys = [entry[0] for entry in self._mib_tree]

    # ------------------------------------------------------------------
    # OID lookups
    # ------------------------------------------------------------------

    def _get_exact(self, oid: tuple) -> Optional[tuple]:
        """Return ``(oid, value)`` if *oid* is in the tree, else ``None``."""
        with self._lock:
            idx = bisect.bisect_left(self._oid_keys, oid)
            if idx < len(self._oid_keys) and self._oid_keys[idx] == oid:
                return self._mib_tree[idx]
        return None

    def _get_next(self, oid: tuple) -> Optional[tuple]:
        """Return the first ``(oid, value)`` whose OID is strictly greater than *oid*."""
        with self._lock:
            idx = bisect.bisect_right(self._oid_keys, oid)
            if idx < len(self._oid_keys):
                return self._mib_tree[idx]
        return None

    # ------------------------------------------------------------------
    # PDU processing
    # ------------------------------------------------------------------

    def _process_get(self, varbinds: list) -> list:
        """Handle a GetRequest: exact OID match for each requested binding."""
        result = []
        for oid_val, _ in varbinds:
            oid = tuple(oid_val)
            match = self._get_exact(oid)
            if match is not None:
                result.append(
                    (v2c.ObjectIdentifier(oid), match[1])
                )
            else:
                result.append(
                    (v2c.ObjectIdentifier(oid), _NO_SUCH_INSTANCE)
                )
        return result

    def _process_getnext(self, varbinds: list) -> list:
        """Handle a GetNextRequest: return the next OID after each requested OID."""
        result = []
        for oid_val, _ in varbinds:
            oid = tuple(oid_val)
            match = self._get_next(oid)
            if match is not None:
                result.append(
                    (v2c.ObjectIdentifier(match[0]), match[1])
                )
            else:
                # End of MIB view -- return the requested OID with endOfMibView
                result.append(
                    (v2c.ObjectIdentifier(oid), _END_OF_MIB_VIEW)
                )
        return result

    def _process_getbulk(
        self,
        varbinds: list,
        non_repeaters: int,
        max_repetitions: int,
    ) -> list:
        """Handle a GetBulkRequest.

        The first *non_repeaters* bindings are treated as GETNEXT (one
        successor each).  The remaining bindings are each walked forward
        up to *max_repetitions* times.
        """
        result = []

        # Clamp to sane limits
        non_repeaters = max(0, min(non_repeaters, len(varbinds)))
        max_repetitions = max(0, min(max_repetitions, 100))

        # Non-repeater portion (single GETNEXT each)
        for oid_val, _ in varbinds[:non_repeaters]:
            oid = tuple(oid_val)
            match = self._get_next(oid)
            if match is not None:
                result.append((v2c.ObjectIdentifier(match[0]), match[1]))
            else:
                result.append((v2c.ObjectIdentifier(oid), _END_OF_MIB_VIEW))

        # Repeater portion
        repeaters = varbinds[non_repeaters:]
        if not repeaters or max_repetitions == 0:
            return result

        # Walk each repeater OID forward up to max_repetitions times
        current_oids = [tuple(oid_val) for oid_val, _ in repeaters]
        for _rep in range(max_repetitions):
            all_end = True
            for i, oid in enumerate(current_oids):
                match = self._get_next(oid)
                if match is not None:
                    result.append((v2c.ObjectIdentifier(match[0]), match[1]))
                    current_oids[i] = match[0]
                    all_end = False
                else:
                    result.append((v2c.ObjectIdentifier(oid), _END_OF_MIB_VIEW))
            if all_end:
                break

        return result

    def _handle_message(self, data: bytes) -> Optional[bytes]:
        """Decode an SNMP v2c message, process it, and return the response bytes.

        Returns ``None`` if the message is malformed or the community
        string does not match.
        """
        try:
            msg, remainder = decoder.decode(data, asn1Spec=v2c.Message())
        except Exception:
            logger.debug("[%s] Failed to decode SNMP message", self.device_id)
            return None

        # Verify community string
        community = str(v2c.apiMessage.getCommunity(msg))
        if community != self.community:
            logger.debug(
                "[%s] Community mismatch: got %r, expected %r",
                self.device_id, community, self.community,
            )
            return None

        # Extract the PDU
        pdu = v2c.apiMessage.getPDU(msg)
        tag = pdu.tagSet

        # Identify PDU type and process
        if tag == _TAG_GET:
            varbinds = v2c.apiPDU.getVarBinds(pdu)
            response_bindings = self._process_get(varbinds)
        elif tag == _TAG_GETNEXT:
            varbinds = v2c.apiPDU.getVarBinds(pdu)
            response_bindings = self._process_getnext(varbinds)
        elif tag == _TAG_GETBULK:
            varbinds = v2c.apiBulkPDU.getVarBinds(pdu)
            non_rep = int(v2c.apiBulkPDU.getNonRepeaters(pdu))
            max_rep = int(v2c.apiBulkPDU.getMaxRepetitions(pdu))
            response_bindings = self._process_getbulk(varbinds, non_rep, max_rep)
        else:
            logger.debug("[%s] Unsupported PDU type: %s", self.device_id, tag)
            return None

        # Build the response PDU
        resp_pdu = v2c.apiPDU.getResponse(pdu)
        v2c.apiPDU.setVarBinds(resp_pdu, response_bindings)

        # Build the response message
        resp_msg = v2c.apiMessage.getResponse(msg)
        v2c.apiMessage.setPDU(resp_msg, resp_pdu)

        try:
            return encoder.encode(resp_msg)
        except Exception:
            logger.exception("[%s] Failed to encode SNMP response", self.device_id)
            return None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the SNMP agent, listening for UDP queries on ``(bind_address, port)``."""
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _SNMPProtocol(self),
            local_addr=(self.bind_address, self.port),
        )
        self._transport = transport
        self._protocol = protocol
        logger.info(
            "[%s] SNMP agent listening on %s:%d",
            self.device_id, self.bind_address, self.port,
        )

    async def stop(self) -> None:
        """Stop the SNMP agent and close the UDP socket."""
        if self._transport is not None:
            self._transport.close()
            self._transport = None
            self._protocol = None
            logger.info("[%s] SNMP agent stopped", self.device_id)

    @property
    def is_running(self) -> bool:
        """Return ``True`` if the agent is currently listening."""
        return self._transport is not None and not self._transport.is_closing()


class _SNMPProtocol(asyncio.DatagramProtocol):
    """asyncio datagram protocol that dispatches to :class:`SNMPAgent`."""

    def __init__(self, agent: SNMPAgent) -> None:
        self._agent = agent
        self._transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
        self._transport = transport

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        response = self._agent._handle_message(data)
        if response is not None and self._transport is not None:
            self._transport.sendto(response, addr)

    def error_received(self, exc: Exception) -> None:
        logger.warning(
            "[%s] UDP error: %s", self._agent.device_id, exc,
        )

    def connection_lost(self, exc: Optional[Exception]) -> None:
        if exc:
            logger.debug(
                "[%s] Connection lost: %s", self._agent.device_id, exc,
            )
