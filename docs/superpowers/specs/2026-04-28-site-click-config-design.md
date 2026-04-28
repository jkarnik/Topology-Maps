# Design: Site-Level Config on Network Click

**Date:** 2026-04-28  
**Status:** Approved

## Problem

Clicking the org row in the ConfigTree shows org-level configs in ConfigAreaViewer. Clicking a network/site row only expands or collapses it — it does not load site-level configs. The behavior should be consistent: any node in the tree that has config data should be selectable.

## Goal

Clicking a network/site in the ConfigTree selects it and shows its config areas in ConfigAreaViewer, while also toggling the tree node open/closed.

## Interaction Model

Option B (approved): one click on the network row does both — selects the network (loads its config) and toggles expand/collapse. No split click targets.

## Changes Required

### `nerdpack/nerdlets/config-app/components/ConfigTree.js`

**`TreeNode` component** — add two optional props:
- `onSelect` (function): called when the row is clicked; if omitted, behavior is unchanged
- `selected` (boolean): when true, applies the same blue highlight used by `EntityItem`

Click handler updated to call both `setOpen(o => !o)` and `onSelect()` (if provided).

Header element gets conditional styling: `color: '#0078bf'` and `background: rgba(0,120,191,0.12)` when `selected` is true.

**Network nodes in the render output** — pass `onSelect` and `selected` to `TreeNode`:
```
onSelect={() => onEntitySelect(net.id, 'network')}
selected={selectedEntityId === net.id}
```

### No other files change

- `ConfigAreaViewer.js`: already queries `WHERE entity_id = '${entityId}'` — network entities have `MerakiConfigSnapshot` records and this query works for them without modification.
- `index.js`: `onEntitySelect` callback already sets both `selectedEntityId` and `selectedEntityType`; no changes needed.

## Data

Networks are stored as `entity_type = 'network'` in `MerakiConfigSnapshot`. Their `entity_id` is the Meraki network ID (e.g. `L_652458996015307332`). Config areas for networks include firewall rules, VLANs, and other network-scoped settings pushed by `config_ingest.py`.

## Out of Scope

- No changes to ChangeHistory, CompareView, or DiffViewer.
- No changes to config_ingest.py or the data model.
