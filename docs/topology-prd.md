# PRD: Network Topology Visualization & Modeling

> **Status:** Draft for engineering review
> **Author:** Product (with Claude)
> **Date:** 2026-06-26
> **Audience:** Engineering team building the topology experience (ingest + New Relic surface)

This PRD consolidates everything learned from building the Topology Maps web UI and then
reproducing that experience inside New Relic. It defines **how network topology should be
modeled as entities and relationships**, **how it should be visualized**, and **how devices,
ports, and components should be tagged**. It is the single reference for the topology workstream.

---

## 1. Overview, Goals & Non-Goals

### What this is

We built a web UI ("Topology Maps") that discovers a Meraki/SNMP network and renders a clean,
hierarchical topology — router/firewall on top, switches in the middle, access points and clients
at the bottom, with stacks folded into single units. We then tried to reproduce that same picture
inside New Relic by pushing entities and relationships. The web UI looks right because it controls
its own layout. New Relic's native entity map does **not** let us control layout, which forced a
semantically dishonest workaround (overloading `CONTAINS`) to fake a hierarchy.

This PRD specifies how to do it **the right way**: a truthful entity/relationship model in New
Relic, plus a controlled rendering surface so the picture matches the web UI without lying in the data.

### Goals

- Define a **single, semantically honest** entity + relationship model for network topology in New Relic.
- Define the **visualization contract**: tier order, layout, port-level connections, grouping of stacks and line cards, and parent/child/sibling semantics.
- Define a **tagging schema** for devices, ports, switch components, and line cards so the topology is filterable and queryable.
- Make the New Relic experience visually match the web UI **without** abusing relationship types.

### Non-Goals

- **No writes back to Meraki or any vendor API.** This is observability/export only — read-only from all vendor sources.
- Not redesigning the existing web UI; it is the reference experience, not the deliverable.
- Not specifying alerting, dashboards, or golden metrics beyond what topology rendering needs.
- Not committing to a specific discovery protocol change (LLDP/SNMP discovery already exists).

### Success criteria

- An engineer can read this doc and know exactly which entity types, relationship types, and tags to create — with no guesswork about `CONTAINS` vs `CONNECTS_TO` vs `MANAGES`.
- The rendered topology in New Relic shows the correct tier hierarchy, port-labeled links, and grouped stacks/line cards.
- Every relationship in the data is true if read directly via NerdGraph/NRQL (no layout hacks in the data layer).

## 2. Background & Key Learnings

These are the hard-won lessons that justify the design choices in this PRD. Engineering should
treat them as settled context, not open debate.

**L1 — The web UI looks right because it owns its layout.** The UI computes tiers and positions
itself (a hierarchical tree: firewall → core → distribution/floor → AP → endpoint) and folds
switch stacks into single nodes. The good look is a property of *our* renderer, not of the data.

**L2 — New Relic's native entity map cannot be styled.** It uses auto/force-directed layout with
no API to pin tiers, order, or positions. The **only** lever over its shape is `CONTAINS` nesting.
Therefore the native map will never match the web UI unless we abuse `CONTAINS`.

**L3 — The original NR implementation faked hierarchy by overloading `CONTAINS`.** It ran a
spanning-tree guess over LLDP links and labeled "uplinks" as `CONTAINS` so the native map would
draw a tree. This is the "hacky" approach we are explicitly moving away from: a switch does not
*contain* another switch.

**L4 — Relationship type must be chosen by meaning, not by how it renders.** New Relic's types
(`CONTAINS`, `CONNECTS_TO`, `MANAGES`, `CALLS`, `IS`, `HOSTS`, etc.) each have a defined meaning.
Picking a type to trick the layout corrupts the data for anyone querying it via NerdGraph/NRQL.

**L5 — `CALLS` and `IS` are wrong for network gear.** `CALLS` is for service-to-service requests
(APM-scoped) and our devices are custom Kentik/Meraki entity types, not service entities — it would
likely be rejected and pollute APM views. `IS` means "the same real-world thing seen twice" and
would make NR *merge* a primary/secondary pair into one entity. Both were considered and rejected.

**L6 — User-defined relationships persist; auto relationships expire.** Relationships created via
the `entityRelationshipUserDefinedCreateOrReplace` NerdGraph mutation persist until explicitly
deleted. Auto-synthesized relationships carry a TTL (≈75 min default). Our topology relationships
must be user-defined, and refresh/cleanup is our responsibility (see §9).

**L7 — Conclusion: separate the data from the picture.** Store an honest model in New Relic, and
render the controlled hierarchy in a surface we own (a topology nerdlet), exactly as we already do
for the config experience. This resolves the tension in L1–L4.

## 3. Architecture — Separate the Data from the Picture

Two layers, with a clean boundary between them.

### 3.1 Data layer — the honest model (source of truth)

All topology entities and relationships live in New Relic, created via NerdGraph user-defined
mutations. Every relationship uses the **semantically correct** type (§7). Nothing in this layer is
shaped to please a renderer. This layer is queryable, trustworthy, and the basis for any future
NRQL, alerting, or third-party consumption.

### 3.2 Presentation layer — a topology nerdlet (the look)

A custom New Relic nerdlet renders the hierarchy with a layout we fully control — top-down tiers,
folded stacks, port-labeled edges — mirroring the web UI's existing layout engine. This is where
"looks correct" is satisfied. It is consistent with the existing config nerdpack
(`nerdpack/nerdlets/`), so it is an additive surface, not a new architecture.

**Recommended decision (to confirm — see §11.3):** the "correct look" lives in the nerdlet, **not**
in the native entity map. We do **not** keep the `CONTAINS` hack. Rationale: it is the only option
that delivers both truthful data *and* the web-UI look, and it matches a pattern already in the repo.

```
            ┌─────────────────────────────┐
 discovery  │   Honest relationship model │   queryable, true,
 (SNMP/     │   in New Relic (NerdGraph)  │   single source of truth
  Meraki) ─▶│   CONTAINS / CONNECTS_TO /  │
            │   MANAGES + tags            │
            └───────────┬─────────────────┘
                        │ read
            ┌───────────┴───────────┐
            ▼                       ▼
  Native entity map        Topology nerdlet  ◀── the deliverable "look"
  (mesh, not styled,        (controlled tiered layout,
   acceptable fallback)      folded stacks, port labels)
```

### 3.3 Reuse

The nerdlet's layout should reuse the web UI's proven logic in
[`ui/src/utils/layoutEngine.ts`](../ui/src/utils/layoutEngine.ts) (tier ranks, stack folding,
AP-to-parent mapping) rather than re-deriving it. The tier/grouping rules in §4–§6 are the contract
both surfaces share.

## 4. Visualization Requirements

### 4.1 Tier order (top → bottom)

The canvas is a **top-down layered hierarchy**. Devices are placed in fixed tiers:

| Tier | Layer | Notes |
|------|-------|-------|
| 0 | **Router / Firewall / Gateway** | Network edge; top of the map |
| 1 | **Core switch** | Collapses upward into tier 0's row if absent |
| 2 | **Distribution switch** | (a.k.a. "floor" switch in the current code) |
| 3 | **Access switch** | Where end devices and APs attach; may equal tier 2 in flat networks |
| 4 | **Access point (AP)** | Wireless |
| 5 | **Endpoint / client** | Wired or wireless clients, leaf nodes |

Rules:
- **Tier collapse:** if a tier has no devices (common in Meraki, which has no core switches), lower
  tiers shift upward so there is no empty band. (Matches existing
  [`HybridView.tsx`](../ui/src/components/HybridView.tsx) `hasCoreSwitches` behavior.)
- **Strict vertical flow:** parents sit above children; an entity is never drawn above its parent.
- **Tier is derived from device role**, not from link direction. The renderer assigns tier by
  device type; links must be consistent with it (see §6 parent/child rules).

### 4.2 Layout behavior

- Top-down tree; siblings spread horizontally under a shared parent; minimize edge crossings.
- A **site/network** acts as the top-level container/grouping for everything beneath it.
- VLANs are shown as a grouping construct associated with their site (not as an inline tier).
- The layout must remain readable at scale (hundreds of devices, ~1,000 ports): support
  collapse/expand of sub-trees (e.g., a switch's ports collapsed by default).

### 4.3 What each node must surface

- Device name, role/type (icon), and status.
- Group affordance for stacks and chassis (see §6).
- Drill-in to ports and components.
- Tag-based filtering (see §8) so users can scope the map (by site, role, VLAN, etc.).

## 5. Connections & Ports

### 5.1 Every physical link is port-to-port

A connection between two devices is a cable between **two specific ports**. The model and the
visualization must both capture the port on **each** side, not just "switch A connects to switch B".

- Each edge carries: `source_device`, `source_port`, `target_device`, `target_port`, and
  `link_type` (e.g., LLDP, stack cable, wireless association).
- The renderer labels each edge end with its port identifier (e.g., `Gi1/0/1 ── Gi2/0/24`), shown
  on hover/selection at minimum, and inline when zoomed in.
- Port identity comes from the port entity (§7). Discovery already has this: LLDP neighbor data
  records the local and remote port; the current ingest encodes the switch serial in the port's
  `service_name` and uses `source_port` for AP attachment.

### 5.2 Link types and how they render

| Link type | Meaning | Relationship type (§7) | Visual |
|-----------|---------|------------------------|--------|
| LLDP uplink | Switch ↔ upstream switch/router | `CONNECTS_TO` | vertical edge between tiers |
| LLDP lateral | Switch ↔ peer (redundancy/cross-link) | `CONNECTS_TO` | edge between same-tier siblings |
| Stack cable | Member chassis ↔ member chassis | (internal — hidden, see §6) | collapsed into the stack node |
| Wireless | Client ↔ AP | `CONNECTS_TO` | dashed edge to leaf |
| Attachment | AP ↔ switch port | `CONTAINS` (port → AP) | edge from port to AP |

### 5.3 Direction

Edge direction encodes uplink vs. downlink (child points to/depends on parent, or vice-versa —
pick one convention and apply it everywhere). Direction is **presentation metadata** used by the
renderer to lay out tiers; it must not change the relationship *type*. Redundant/lateral links have
no parent/child direction and render as sibling links.

## 6. Grouping & Hierarchy Semantics

### 6.1 The governing rule — "can it exist on its own?"

Use this single test to choose how two things relate:

- **Physically part of the parent; cannot exist independently → `CONTAINS`** (parent → child).
- **A separate device the parent controls → `MANAGES`** (controller → controlled).
- **Peers joined by a cable → `CONNECTS_TO`** (no parent/child).

### 6.2 Switch stacks (separate chassis cabled together)

A stack is multiple **independent switch chassis** acting as one logical unit; one member is
active/master. Each member is a real switch (unplug it, it still works).

- **Model:** `active member ──MANAGES──▶ each other member`. The active controls the stack; members
  are separate devices, so this is `MANAGES`, not `CONTAINS`.
- **Visualization:** fold the whole stack into **one grouped node** (a stack unit) on the canvas,
  exactly as the web UI does (members share a `stack_name`; the active is chosen by `stack_role`;
  internal stack cables are hidden). Expanding the group reveals the member chassis.

### 6.3 Line cards (modules inside one chassis)

A line card is a module slotted into a single chassis. Pull it out and it is a dead board — it
**cannot** exist on its own.

- **Model:** `chassis ──CONTAINS──▶ line card`. (The supervisor "managing" the cards is real but
  secondary; structural containment is the truth we model.)
- **Visualization:** line cards are grouped **inside** their chassis node; expanding the chassis
  reveals cards, and expanding a card reveals its ports.

### 6.4 Ports

A port cannot exist without its switch/line card — a structural sub-component.

- **Model:** `switch (or line card) ──CONTAINS──▶ port`. (Already implemented as "Switch CONTAINS
  Port".) If line cards are modeled, ports hang off the card: `switch ▶ card ▶ port ▶ AP`.

### 6.5 Parent / child / sibling — precise definitions

- **Parent:** the entity on the source side of a `CONTAINS` (it owns the child) **or** a `MANAGES`
  (it controls the child). Drawn one tier above the child.
- **Child:** the target of a `CONTAINS`/`MANAGES`. A child has exactly one structural parent
  (a port belongs to one switch; a line card to one chassis; a stack member to one active).
- **Sibling:** two entities that share the same parent **or** are joined by a `CONNECTS_TO` with no
  parent/child direction (e.g., two core switches cross-linked for redundancy). Siblings render on
  the same tier; their link is a lateral edge, never a hierarchy edge.

### 6.6 Worked example

```
Site
 └─CONTAINS─ Firewall
 └─CONTAINS─ Core stack (grouped node)
              ├─ Active SW ─MANAGES─▶ Member SW       (separate chassis, folded into the group)
              └─ Active SW ─CONTAINS─▶ Line card ─CONTAINS─▶ Port ─CONTAINS─▶ AP
 Firewall ─CONNECTS_TO─ Core stack        (uplink cable: port-to-port)
 Core SW  ─CONNECTS_TO─ Core SW           (lateral redundancy: siblings)
 Client   ─CONNECTS_TO─ AP                (wireless)
```

## 7. Entity & Relationship Model

### 7.1 Entity types

| Entity | Represents | Status |
|--------|------------|--------|
| Site / Network | A location/Meraki network; top-level container | exists |
| Router / Firewall / Gateway | Network edge device | exists (firewall) |
| Core switch | Tier-1 switch | exists |
| Distribution / floor switch | Tier-2 switch | exists |
| Access switch | Tier-3 switch | exists (as floor switch today) |
| Access point | Wireless AP | exists |
| Endpoint / client | Leaf device | exists |
| VLAN | Layer-2 segment, grouped under a site | exists |
| Port | A physical switch/AP port | exists (`MerakiSwitchPort`) |
| Stack | Logical grouping of member chassis | **derived** (via `stack_name`); modeled by `MANAGES`, no separate entity required |
| Line card | A module within a modular chassis | **new** — only needed when modular/chassis gear is ingested |

> Meraki switches are fixed-config (no line cards). Line cards are a forward-looking addition for
> modular/chassis platforms and are not required for the current Meraki dataset.

### 7.2 Relationship-type catalog (only these three are used)

| Type | Meaning | Used for |
|------|---------|----------|
| `CONTAINS` | B is physically part of A | Site→device, Chassis→line card, Switch/Card→Port, Port→AP |
| `CONNECTS_TO` | A and B are cabled peers | Switch↔switch (uplink + lateral), Client↔AP |
| `MANAGES` | A is a separate device that controls B | Stack active→members, Primary firewall→secondary |

### 7.3 Explicitly rejected types (do not use)

- **`CALLS`** — service-to-service (APM) semantics; our entities are custom Kentik/Meraki types, not
  service entities. Wrong meaning and likely rejected/non-rendering. (See L5.)
- **`IS`** — means "the same real-world thing"; would merge a primary/secondary pair into one
  entity. Never use for distinct devices. (See L5.)
- **Overloaded `CONTAINS` on uplinks** — the abandoned hack. Uplinks are `CONNECTS_TO`. (See L3.)

### 7.4 Authoritative source for allowed types

Relationship types and the subset valid for user-defined relationships should be confirmed against
the **NerdGraph schema** (`EntityRelationshipEdgeType` enum and the user-defined mutation input
type) — the schema is authoritative over prose docs. `CONTAINS`/`CONNECTS_TO` are proven to work in
this repo today; **`MANAGES` for these custom entity types must be verified** before relying on it
(see Open Questions §11).

## 8. Tagging Requirements

Tags make the topology filterable, groupable, and queryable, and they drive the relationship
derivation (e.g., `network_id` groups devices under a site). Every entity carries a common set plus
type-specific tags.

### 8.1 Common tags (all entities)

| Tag | Purpose |
|-----|---------|
| `source` | Provenance marker (e.g., `topology-maps-app`) for scoping NRQL/cleanup |
| `network_id` / `site_id` | The site/network the entity belongs to (drives Site `CONTAINS`) |
| `site_name` | Human-readable site |
| `role` / `tier` | Device role used for tier placement (router, core, distribution, access, ap, client) |
| `vendor`, `model` | Hardware identity |
| `serial` | Unique hardware serial (join key across ports/components) |
| `status` | Operational status surfaced on the node |

### 8.2 Type-specific tags

- **Device (switch/router/AP):** `mgmt_ip`, `mac`, `firmware`, and `stack_name` + `stack_role`
  (`active`/`member`) when part of a stack.
- **Port:** `parent_serial` (owning switch/card), `port_id` (e.g., `Gi1/0/1`), `speed`, `duplex`,
  `vlan`/`native_vlan`, `link_type` (lldp/stack/access/trunk), `neighbor_serial` + `neighbor_port`
  (the far end of the cable), `admin_status`, `oper_status`.
- **Switch component / line card:** `parent_serial` (chassis), `slot`, `component_type`
  (`linecard`/`supervisor`/`psu`/`fan` as applicable), `model`.
- **Stack (derived):** members share `stack_name`; `stack_role` distinguishes active vs member.
- **Site / Network:** `network_id`, `org_id`, `address`/`region` if available.
- **VLAN:** `vlan_id`, `name`, `subnet`, `network_id`.

### 8.3 Tagging principles

- **Tags are the join keys.** Relationships are derived from tags (`network_id`, `parent_serial`,
  `neighbor_serial`/`neighbor_port`, `stack_name`), so these must be present and consistent at ingest.
- **Do not set New Relic reserved attributes** (`entity.guid`, `entity.name`, `entity.type`) unless
  deliberately overriding identity — doing so can mis-associate or duplicate entities.
- Tag values should be stable across sweeps so entities and relationships are updated, not recreated.

## 9. Data Flow, Ingest & Freshness

### 9.1 Pipeline

1. **Discover** topology (existing SNMP/LLDP collector + Meraki data) into the app DB.
2. **Push entities** to New Relic as custom events/metrics with the tags in §8 (existing
   `push_all_devices.py` pattern).
3. **Derive relationships** from tags/discovery (site membership, port ownership, LLDP
   neighbor pairs, stack membership, HA pairing) and create them via
   `entityRelationshipUserDefinedCreateOrReplace` (existing `create_relationships.py` pattern,
   re-typed per §6–§7).
4. **Render** in the topology nerdlet from the entities + relationships (+ port/edge metadata).

### 9.2 Freshness & lifecycle (critical)

- User-defined relationships **persist until deleted** — they do not auto-expire. The ingest must
  **reconcile**: create/replace current relationships and **delete** stale ones (removed cables,
  decommissioned devices) on each sweep, or the map drifts from reality.
- Entities have a TTL (`entityExpirationTime`); keep telemetry flowing so active entities don't
  expire, and ensure relationships are re-asserted on the schedule that keeps maps fresh. (This
  mirrors the known New Relic map-freshness behavior already handled by the scheduler.)
- Re-pushing must be **idempotent**: stable GUIDs/tags so a sweep updates rather than duplicates.

### 9.3 Edge/port metadata storage

Port-to-port detail (source/target port, link_type, direction) must be available to the renderer.
Carry it as relationship attributes and/or port-entity tags (`neighbor_serial`, `neighbor_port`),
so the nerdlet can label both ends of every edge without re-querying discovery.

## 10. Constraints

- **Read-only from Meraki/vendor APIs.** Never write back to Meraki or any vendor API — observability
  and export only.
- **New Relic native map is not styleable.** The web-UI look is delivered by the nerdlet, not the
  native entity map (which remains an acceptable, if mesh-like, fallback view).
- **`MERAKI_API_KEY` gates config collection** (existing constraint); topology discovery has its own
  seed/credentials.
- **Relationship types are limited to what NerdGraph allows** for user-defined relationships; the
  design uses only `CONTAINS`/`CONNECTS_TO`/`MANAGES` and must degrade gracefully if `MANAGES` is
  unavailable (see §11).

## 11. Open Questions & Decisions for Engineering

1. **`MANAGES` support (blocking for stacks/HA).** Confirm via the NerdGraph schema whether
   `entityRelationshipUserDefinedCreateOrReplace` accepts `MANAGES` for our custom entity types. If
   not, the fallback is `CONTAINS` (active→members) for stacks and a tag-only marker for HA pairs.
   *Recommended first step: a read-only probe that attempts one `MANAGES` relationship and reports
   acceptance.*
2. **Distribution vs. access tier in Meraki.** Meraki networks are mostly flat (no core, often no
   true distribution layer). Decide how `role`/`tier` is assigned when the physical role is
   ambiguous — by uplink depth, by model, or by explicit tag.
3. **Nerdlet vs. native map scope.** Confirm the nerdlet is the primary surface and the native map
   is fallback-only (this PRD assumes yes). Confirm whether the nerdlet reads relationships from NR
   or topology directly from the app DB/API.
4. **Line-card ingestion timing.** Line cards are specified but not in scope for the Meraki dataset.
   Decide whether to build the entity/tag schema now (forward-compatible) or defer until modular
   gear is onboarded.
5. **Edge metadata location.** Decide whether port-to-port edge detail lives on relationship
   attributes, port-entity tags, or both (§9.3).
6. **Scale targets.** Confirm the largest expected topology (device/port counts) so the renderer's
   collapse/virtualization strategy is sized correctly.

## 12. Appendix — Glossary & References

### Glossary

- **Stack** — multiple independent switch chassis cabled together, acting as one logical unit; one
  member is active/master.
- **Line card** — a module installed in a slot of a modular chassis; cannot operate standalone.
- **Uplink** — a link toward the network core/edge (child→parent direction).
- **Lateral link** — a same-tier link between siblings (redundancy/cross-connect), no hierarchy.
- **Tier** — the horizontal band an entity occupies based on its role (router → core → distribution
  → access → AP → client).

### Relationship cheat-sheet

| Pair | Type |
|------|------|
| Site → device | `CONTAINS` |
| Chassis → line card | `CONTAINS` |
| Switch / line card → port | `CONTAINS` |
| Port → AP | `CONTAINS` |
| Switch ↔ switch (uplink & lateral) | `CONNECTS_TO` |
| Client → AP | `CONNECTS_TO` |
| Stack active → member | `MANAGES` |
| Primary firewall → secondary | `MANAGES` |

### Existing code references

- Tier ranks, stack folding, AP-to-parent mapping — [`ui/src/utils/layoutEngine.ts`](../ui/src/utils/layoutEngine.ts)
- Tier Y-positions and core-collapse behavior — [`ui/src/components/HybridView.tsx`](../ui/src/components/HybridView.tsx)
- Device/link types — [`ui/src/types/topology.ts`](../ui/src/types/topology.ts)
- Entity push + event types/tags — [`nr_ingest/push_all_devices.py`](../nr_ingest/push_all_devices.py)
- Relationship creation/deletion via NerdGraph — [`nr_ingest/create_relationships.py`](../nr_ingest/create_relationships.py)
- NR entity/relationship reference — [`docs/reference/new-relic-entity-types.md`](reference/new-relic-entity-types.md)
- Map freshness behavior — [`docs/nr-ingest-status.md`](nr-ingest-status.md)
