# Config Normalization Catalog — Design Spec

## Overview

Golden templates for device config (Gateway, Switch, AP) need clean data — fields that are unique per device (serial numbers, IP addresses, BLE identifiers) must be stripped before they reach a template or a compliance score. Without this, every device would show constant false-positive drift on fields that can never match.

This spec defines a normalization catalog that strips known-noise fields at collection time, using the same pattern as the existing `REDACTION_PATHS` catalog for secrets.

## Background

The existing config collector stores raw API responses as blobs in `config_observations`. Secrets (PSKs, RADIUS secrets, SNMP community strings) are already stripped at collection time by `redactor.py` using `REDACTION_PATHS` in `redaction_catalog.py`. This spec adds a parallel `NORMALIZATION_PATHS` catalog for non-secret per-device identity fields.

Stripping happens at collection time (Option A) so templates and scoring queries work with clean data — no special handling needed at template creation or scoring time.

## What Gets Excluded vs Stripped

### Area excluded from templates entirely

| Config Area | Reason |
|---|---|
| `device_metadata` | Serial, name, MAC, networkId, lat/lng, address, lanIp — all identity/location. Nothing is templatable. Observations are still collected and stored; this area is simply never included when `create_template` builds template areas. |

### Fields stripped at collection time (NORMALIZATION_PATHS)

#### `device_management_interface`
| Field | Reason |
|---|---|
| `ddnsHostname` | Unique per device |
| `wan1.staticIp`, `wan1.staticGateway` | Unique per device |
| `wan2.staticIp`, `wan2.staticGateway` | Unique per device |

What remains: `wan1.usingStaticIp`, `wan1.vlan`, `wan2.usingStaticIp`, `wan2.vlan` — whether each WAN is DHCP or static, and which VLAN.

#### `switch_device_ports`
| Field | Reason |
|---|---|
| `[*].linkNegotiationCapabilities` | Read-only hardware capability list, not a setting |

All other fields kept: `portId` (used as row identity key by diff engine), `vlan`, `allowedVlans`, `poeEnabled`, `stpGuard`, `type`, `enabled`, `accessPolicyType`, `udld`, `name`. Port `name` is intentionally kept — operators set it deliberately and drift is real signal.

#### `switch_device_warm_spare`
| Field | Reason |
|---|---|
| `spareSerial` | Serial of the paired HA device — unique per install |

What remains: `enabled`, `mode`.

#### `switch_device_routing_interfaces`
| Field | Reason |
|---|---|
| `[*].interfaceId` | Internal Meraki ID |
| `[*].ip` | Unique per device |
| `[*].subnet` | Unique per site |
| `[*].defaultGateway` | Unique per site |

What remains: `name`, `vlanId`, `ospfSettings` (area/cost/enabled), `multicastRouting`.

#### `switch_device_routing_static_routes`
| Field | Reason |
|---|---|
| `[*].staticRouteId` | Internal Meraki ID |
| `[*].nextHopIp` | Unique per site |
| `[*].subnet` | Destination subnet is site-specific |

What remains: `name`, `advertiseViaOspf`, `preferOverOspfRoutes`. Scoring will detect "template has 3 static routes, device has 0" as drift at the array level.

#### `wireless_device_bluetooth`
| Field | Reason |
|---|---|
| `uuid` | Unique per AP |
| `major` | BLE beacon identifier |
| `minor` | BLE beacon identifier |

What remains: `advertisingEnabled`, `scanningEnabled`.

## Implementation

### Files changed

| File | Change |
|---|---|
| `server/config_collector/redaction_catalog.py` | Add `NORMALIZATION_PATHS` dict |
| `server/config_collector/redactor.py` | Add `normalize()` function; deletes fields rather than replacing with `[REDACTED]` |
| `server/config_collector/scanner.py` | Call `normalize()` after `redact()`, before hashing and storing the blob |
| `server/config_collector/store.py` | `create_template` filters out `device_metadata` from template areas |

### NORMALIZATION_PATHS shape

Same format as `REDACTION_PATHS` — a dict of `config_area → list[str]` where each string is a dot-path with optional `[*]` array wildcard:

```python
NORMALIZATION_PATHS: dict[str, list[str]] = {
    "device_management_interface": [
        "ddnsHostname",
        "wan1.staticIp",
        "wan1.staticGateway",
        "wan2.staticIp",
        "wan2.staticGateway",
    ],
    "switch_device_ports": [
        "[*].linkNegotiationCapabilities",
    ],
    "switch_device_warm_spare": [
        "spareSerial",
    ],
    "switch_device_routing_interfaces": [
        "[*].interfaceId",
        "[*].ip",
        "[*].subnet",
        "[*].defaultGateway",
    ],
    "switch_device_routing_static_routes": [
        "[*].staticRouteId",
        "[*].nextHopIp",
        "[*].subnet",
    ],
    "wireless_device_bluetooth": [
        "uuid",
        "major",
        "minor",
    ],
}
```

### normalize() behavior

`normalize(config_area, payload_dict)` deletes (not redacts) each listed field path from the payload. The path walker is the same leniency as the redactor: if a path doesn't resolve (field absent, array empty), it is silently skipped. Returns the mutated dict.

### Scanner integration

In `scanner.py`, after `redact()` and before computing the blob hash:

```python
payload = redact(config_area, payload)
payload = normalize(config_area, payload)
blob_hash = hash_payload(payload)
```

Because normalization happens before hashing, re-collecting a device after the catalog is deployed will produce a different hash than the pre-normalization observation. This is expected — the new hash is the correct one and the old observation is superseded on the next collection run.

## Out of Scope

- Normalization of network-scoped or org-scoped areas (they have their own redaction rules and no per-device identity fields)
- Firmware version tracking — `device_metadata` is excluded from templates; a future spec can add firmware compliance separately
- Camera device areas — no per-device identity fields identified; no normalization needed
