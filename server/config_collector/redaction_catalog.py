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
