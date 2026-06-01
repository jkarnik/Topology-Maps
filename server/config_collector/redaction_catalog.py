"""Map of config_area → JSON paths that must be redacted before storage.

Path syntax is a simple dot-and-bracket notation:
  - `foo.bar` — nested key access
  - `foo[*].bar` — for every item in the `foo` array, access `.bar`
  - `foo.bar[*]` — `foo.bar` is an array whose items are themselves replaced

The walker in `redactor.py` interprets these paths leniently: if a path
does not resolve against a particular response (e.g. field absent,
array empty), it is silently skipped.

This catalog is THE authoritative list of known secret fields.
Reviewed quarterly; updated whenever Meraki adds or renames endpoints.
"""
from __future__ import annotations

REDACTION_PATHS: dict[str, list[str]] = {
    # Per-SSID PSKs and RADIUS secrets (on the list endpoint)
    "wireless_ssids": [
        "[*].psk",
        "[*].radiusServers[*].secret",
        "[*].radiusAccountingServers[*].secret",
    ],
    # Identity PSK passphrases (per-SSID sub-endpoint)
    "wireless_ssid_identity_psks": [
        "[*].passphrase",
    ],
    # Site-to-site VPN pre-shared keys
    "appliance_site_to_site_vpn": [
        "peers[*].secret",
        "peers[*].ikev2.secret",
    ],
    # Network-level SNMP community/user passphrases
    "network_snmp": [
        "communityString",
        "users[*].passphrase",
    ],
    # Org-level SNMP
    "org_snmp": [
        "v2CommunityString",
        "users[*].passphrase",
    ],
    # Webhook HTTP server shared secrets
    "network_webhooks_http_servers": [
        "[*].sharedSecret",
    ],
}

NORMALIZATION_PATHS: dict[str, list[str]] = {
    # Per-device identity fields in management interface
    "device_management_interface": [
        "ddnsHostname",
        "wan1.staticIp",
        "wan1.staticGateway",
        "wan2.staticIp",
        "wan2.staticGateway",
    ],
    # Read-only hardware capability list — not a setting
    "switch_device_ports": [
        "[*].linkNegotiationCapabilities",
    ],
    # Serial of the paired HA device — unique per install
    "switch_device_warm_spare": [
        "spareSerial",
    ],
    # Per-device/site IP addresses and internal Meraki IDs
    "switch_device_routing_interfaces": [
        "[*].interfaceId",
        "[*].ip",
        "[*].subnet",
        "[*].defaultGateway",
    ],
    # Site-specific routing details and internal IDs
    "switch_device_routing_static_routes": [
        "[*].staticRouteId",
        "[*].nextHopIp",
        "[*].subnet",
    ],
    # Per-AP BLE beacon identifiers
    "wireless_device_bluetooth": [
        "uuid",
        "major",
        "minor",
    ],
}
