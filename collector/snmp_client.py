"""Async SNMP client for querying simulator agents.

Builds SNMPv2c request PDUs, sends them as UDP datagrams, and decodes
the responses.  Supports GET, GETNEXT, and WALK operations using the
same BER encoding that :mod:`simulator.agent` expects.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Optional

from pyasn1.codec.ber import decoder, encoder
from pysnmp.proto.api import v2c
from pysnmp.proto.rfc1902 import ObjectIdentifier, OctetString
from pysnmp.proto.rfc1905 import EndOfMibView, NoSuchInstance, NoSuchObject

logger = logging.getLogger(__name__)

# Timeout for a single SNMP request (seconds)
_REQUEST_TIMEOUT = 3.0


def _oid_str_to_tuple(oid: str) -> tuple[int, ...]:
    """Convert a dotted OID string to a tuple of ints."""
    if oid.startswith("."):
        oid = oid[1:]
    return tuple(int(p) for p in oid.split("."))


def _oid_tuple_to_str(oid: tuple[int, ...]) -> str:
    """Convert an OID tuple to a dotted string."""
    return ".".join(str(i) for i in oid)


def _is_end_of_mib(value) -> bool:
    """Return True if the value signals end-of-MIB-view or no-such-*."""
    return isinstance(value, (EndOfMibView, NoSuchInstance, NoSuchObject))


class SNMPClient:
    """Async SNMP v2c client that communicates with simulator agents via UDP.

    All agents run on localhost at different ports, sharing a single
    community string.
    """

    def __init__(self, host: str = "127.0.0.1", community: str = "public"):
        self.host = host
        self.community = community
        self._request_id = random.randint(1, 2**16)

    def _next_request_id(self) -> int:
        self._request_id = (self._request_id + 1) % (2**31)
        return self._request_id

    # ------------------------------------------------------------------
    # Low-level transport
    # ------------------------------------------------------------------

    async def _send_and_receive(self, port: int, message_bytes: bytes) -> Optional[bytes]:
        """Send a UDP datagram and wait for the response."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bytes] = loop.create_future()

        class _ClientProtocol(asyncio.DatagramProtocol):
            def __init__(self):
                self.transport: Optional[asyncio.DatagramTransport] = None

            def connection_made(self, transport: asyncio.DatagramTransport) -> None:
                self.transport = transport

            def datagram_received(self, data: bytes, addr: tuple) -> None:
                if not future.done():
                    future.set_result(data)

            def error_received(self, exc: Exception) -> None:
                if not future.done():
                    future.set_exception(exc)

            def connection_lost(self, exc: Optional[Exception]) -> None:
                if exc and not future.done():
                    future.set_exception(exc)

        transport, protocol = await loop.create_datagram_endpoint(
            _ClientProtocol,
            remote_addr=(self.host, port),
        )

        try:
            transport.sendto(message_bytes)
            return await asyncio.wait_for(future, timeout=_REQUEST_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning("SNMP request to port %d timed out", port)
            return None
        except Exception as exc:
            logger.warning("SNMP request to port %d failed: %s", port, exc)
            return None
        finally:
            transport.close()

    # ------------------------------------------------------------------
    # PDU builders
    # ------------------------------------------------------------------

    def _build_get_message(self, oid: str) -> bytes:
        """Build an SNMPv2c GetRequest message."""
        pdu = v2c.GetRequestPDU()
        v2c.apiPDU.setDefaults(pdu)
        v2c.apiPDU.setRequestID(pdu, v2c.Integer(self._next_request_id()))
        v2c.apiPDU.setVarBinds(
            pdu,
            [(v2c.ObjectIdentifier(_oid_str_to_tuple(oid)), v2c.null)],
        )

        msg = v2c.Message()
        v2c.apiMessage.setDefaults(msg)
        v2c.apiMessage.setCommunity(msg, v2c.OctetString(self.community))
        v2c.apiMessage.setPDU(msg, pdu)

        return encoder.encode(msg)

    def _build_getnext_message(self, oid: str) -> bytes:
        """Build an SNMPv2c GetNextRequest message."""
        pdu = v2c.GetNextRequestPDU()
        v2c.apiPDU.setDefaults(pdu)
        v2c.apiPDU.setRequestID(pdu, v2c.Integer(self._next_request_id()))
        v2c.apiPDU.setVarBinds(
            pdu,
            [(v2c.ObjectIdentifier(_oid_str_to_tuple(oid)), v2c.null)],
        )

        msg = v2c.Message()
        v2c.apiMessage.setDefaults(msg)
        v2c.apiMessage.setCommunity(msg, v2c.OctetString(self.community))
        v2c.apiMessage.setPDU(msg, pdu)

        return encoder.encode(msg)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(self, data: bytes) -> list[tuple[str, object]]:
        """Decode an SNMP response and return a list of (oid_str, value) pairs.

        Returns an empty list on decode failure.  End-of-MIB-view /
        noSuchInstance sentinels are returned as-is so callers can detect them.
        """
        try:
            msg, _ = decoder.decode(data, asn1Spec=v2c.Message())
        except Exception:
            logger.debug("Failed to decode SNMP response")
            return []

        pdu = v2c.apiMessage.getPDU(msg)

        # Check for SNMP error status
        error_status = int(v2c.apiPDU.getErrorStatus(pdu))
        if error_status != 0:
            logger.debug("SNMP error status: %d", error_status)
            return []

        varbinds = v2c.apiPDU.getVarBinds(pdu)
        result: list[tuple[str, object]] = []
        for oid_val, val in varbinds:
            oid_str = _oid_tuple_to_str(tuple(oid_val))
            result.append((oid_str, val))
        return result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get(self, port: int, oid: str) -> Optional[tuple[str, object]]:
        """SNMP GET -- returns (oid_str, value) or None on failure."""
        msg_bytes = self._build_get_message(oid)
        resp = await self._send_and_receive(port, msg_bytes)
        if resp is None:
            return None

        varbinds = self._parse_response(resp)
        if not varbinds:
            return None

        oid_str, val = varbinds[0]
        if _is_end_of_mib(val):
            return None
        return (oid_str, val)

    async def get_next(self, port: int, oid: str) -> Optional[tuple[str, object]]:
        """SNMP GETNEXT -- returns (oid_str, value) for the next OID, or None."""
        msg_bytes = self._build_getnext_message(oid)
        resp = await self._send_and_receive(port, msg_bytes)
        if resp is None:
            return None

        varbinds = self._parse_response(resp)
        if not varbinds:
            return None

        oid_str, val = varbinds[0]
        if _is_end_of_mib(val):
            return None
        return (oid_str, val)

    async def walk(self, port: int, oid_prefix: str) -> list[tuple[str, object]]:
        """SNMP WALK -- returns list of (oid_str, value) pairs under the prefix.

        Walks using repeated GETNEXT requests until the returned OID
        leaves the prefix subtree or end-of-MIB-view is reached.
        """
        # Normalise prefix for comparison (strip leading dot)
        prefix = oid_prefix.lstrip(".")
        results: list[tuple[str, object]] = []
        current_oid = oid_prefix

        while True:
            pair = await self.get_next(port, current_oid)
            if pair is None:
                break

            oid_str, val = pair
            # Check whether the returned OID is still under the prefix subtree.
            # The returned OID must start with the prefix followed by a dot
            # (or be exactly the prefix, though that shouldn't happen with GETNEXT).
            normalised = oid_str.lstrip(".")
            if not (normalised == prefix or normalised.startswith(prefix + ".")):
                break

            results.append((oid_str, val))
            current_oid = oid_str

        return results
