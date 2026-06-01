# Device Golden Templates — Design Spec

## Overview

Extends the Compare Templates feature to support device-level golden templates for Gateway, Switch, and Access Point device types. Previously all templates were promoted from a network's config. This change allows templates to be built from a specific device's own config, enabling per-device compliance scoring grouped by network.

## Background

Templates have four kinds:
- **Site** — network-level config (existing behavior, unchanged)
- **Gateway** — MX/appliance device config
- **Switch** — MS/switch device config
- **Access Point** — MR/wireless device config

Each kind maps to a different set of config areas collected from the Meraki API:

| Kind | Config area prefix | API scope |
|---|---|---|
| Site | all network-level areas | `entity_type = network` |
| Gateway | `appliance_device_*` | `entity_type = device`, appliance product |
| Switch | `switch_device_*` | `entity_type = device`, switch product |
| Access Point | `wireless_device_*` | `entity_type = device`, wireless product |

## Data Model

### `config_templates` table — two new columns

```sql
source_device_serial  TEXT   -- null for Site templates; serial of golden device for Gateway/Switch/AP
source_device_name    TEXT   -- display name of the golden device (best-effort from observations)
```

Both columns are added via `ALTER TABLE … ADD COLUMN` migration (no-op if already present). Existing Site templates are unaffected (`NULL` in both columns).

`config_template_areas` is unchanged. For device templates, the rows in this table come from `entity_type='device'` observations for the chosen serial rather than from network observations.

### Device-to-network mapping

Config observations do not store a `network_id` for device-scope records. The scoring endpoint resolves device→network by calling the Meraki `/organizations/{org_id}/inventory/devices` API (same pattern used by the existing `/api/config/tree` endpoint). This is best-effort: devices not present in the inventory response are grouped under an "Unknown network" bucket.

## Backend Changes

### New endpoint — device list for promote modal

```
GET /api/config/devices-for-template?org_id=&network_id=&kind=
```

Returns devices of the matching kind that have been observed in the given network. Device kind is detected from which config areas exist in `config_observations`:
- `gateway` → devices with any `appliance_device_*` area
- `switch` → devices with any `switch_device_*` area
- `access_point` → devices with any `wireless_device_*` area

Response:
```json
[{ "serial": "Q2KD-XXXX-0001", "name": "Core-SW-01" }, …]
```

### Modified `POST /api/config/templates`

`PromoteTemplateRequest` gains two optional fields:
- `device_serial: str | None` — required when kind is not `site`
- `device_name: str | None` — optional display name hint

When `device_serial` is present, the store function queries `entity_type='device', entity_id=device_serial` observations instead of network observations.

### Modified `GET /api/config/templates/{id}/scores`

Detects whether the template is a device template (`source_device_serial IS NOT NULL`). If so:

1. Fetches all `entity_type='device'` observations matching the template's config areas
2. Calls Meraki inventory API to resolve each serial → network
3. Scores each device against the template areas (same diff logic as today)
4. Returns results grouped by network

Response shape changes for device templates:

```json
{
  "template": { "id": 1, "name": "Standard Core Switch", "area_count": 8, "kind": "switch" },
  "networks": [
    {
      "network_id": "N_123",
      "network_name": "NYC – Flagship Store",
      "aggregate_score": 74,
      "device_count": 3,
      "devices": [
        { "serial": "Q2KD-0001", "name": "Core-SW-01", "score_pct": 97, "missing_areas": [], "area_scores": […] },
        { "serial": "Q2KD-0002", "name": "Floor-SW-02", "score_pct": 68, "missing_areas": [], "area_scores": […] }
      ]
    }
  ]
}
```

Site templates continue to use the existing flat `scores: NetworkTemplateScore[]` response shape.

## Frontend Changes

### Types (`types/config.ts`)

- `ConfigTemplate` gains `source_device_serial: string | null` and `source_device_name: string | null`
- New type `DeviceTemplateScore` for individual device scores
- New type `NetworkDeviceScores` for the grouped-by-network scoring response
- New type `DeviceTemplateScoresResponse` for the full device-template scores response

### API (`api/compare.ts`)

- `createTemplate` gains `deviceSerial: string | null` parameter
- New `listDevicesForTemplate(orgId, networkId, kind)` → `Promise<{serial, name}[]>`
- `getTemplateScores` return type is a union of the existing flat response and the new grouped response

### Hook (`hooks/useTemplates.ts`)

- `promote` gains `deviceSerial: string | null` parameter
- New `useDevicesForTemplate(orgId, networkId, kind)` hook for the device picker

### `TemplatesView.tsx` — Promote modal

When kind is not `site`, the modal adds two steps before the name field:

1. **Network picker** — dropdown of all networks (from `ConfigTree`)
2. **Device picker** — list of devices returned by `listDevicesForTemplate` for the chosen network and kind; shows device name + serial; selecting one highlights it

The Save button remains disabled until name, network, and device are all filled.

### `TemplatesView.tsx` — Scoring panel

For device templates (`source_device_serial` is set), `useTemplateScores` returns the new grouped response. The `ScoresPanel` component renders:

- One collapsible row per network (sorted by aggregate score ascending — worst first)
- Each row header shows: network name, device count, aggregate score with color coding
- Expanded row shows individual device score bars (same `ScoreBar` component)
- Clicking a device row shows its area-level breakdown (same pattern as current `NetworkScoreRow`)

Site template scoring is unchanged.

## Out of Scope

- Editing a template after creation (not supported for either kind today)
- Nerdpack changes (will be done in a follow-up once the UI is finalized)
- Meraki API unavailability handling beyond the existing best-effort pattern
