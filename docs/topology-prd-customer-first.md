# PRD: Network Topology in the Observability Platform

> **Status:** Draft for engineering review
> **Author:** Product
> **Date:** 2026-06-29
> **Audience:** Engineering team (and, where needed, the New Relic platform team)

This PRD describes **what the customer wants** from a network topology experience inside their
observability platform — stated from first principles, in terms of outcomes and desired experience,
**not** implementation. *How* to deliver it is engineering's call: with existing platform
primitives, or by partnering with the New Relic platform team to introduce new kinds of entities
and relationships where today's primitives don't fit.

A prior internal project prototyped much of this and produced concrete technical recommendations.
That work is **not** the requirement — it is captured in the **Appendix** as reference only.

---

## 1. Purpose & Framing

The customer wants to understand their physical and logical network at a glance, inside the same
platform where they already watch performance and health. This PRD defines that experience purely
in terms of what the customer should be able to see, do, and trust.

**Division of responsibility:**

- **Product owns the "what":** the experience, the customer's mental model, the outcomes below.
- **Engineering owns the "how":** data modeling, rendering, and platform choices. Engineering
  decides whether existing entity/relationship primitives are sufficient, or whether to work with
  the **New Relic platform team to define new kinds of entities and relationships** purpose-built
  for network topology. Either path is acceptable as long as the customer outcomes are met.

Nothing in the body of this document should be read as prescribing a specific entity type,
relationship type, API, or rendering surface. Where the prior prototype made such choices, they are
in the Appendix as a starting reference — useful, but not binding.

## 2. The Customer & Their Problem

**Who:** Network and IT operations teams who run multi-site networks (firewalls/routers, switches,
wireless) and already use the observability platform for monitoring.

**The job to be done:** *"When something is wrong, or when I'm planning a change, I want to see my
network the way it is physically wired and logically organized — without exporting to a separate
tool or holding the diagram in my head."*

**Today's pain:**

- The network's structure lives in people's heads, static Visio diagrams, or a separate NMS — none
  of which sit next to the telemetry that tells them something is broken.
- When a device or link degrades, they can't immediately see what's upstream, downstream, or
  redundant — so blast radius and root cause are guesswork.
- Inventory (which device, which port, which site, which VLAN) is disconnected from the live map.

**The desired outcome:** one always-current topology view, in the observability platform, that
mirrors how the customer actually thinks about their network — and that they can filter, drill into,
and trust.

## 3. Goals & Non-Goals

### Goals (customer outcomes)

- The customer can open a **topology map** of their network inside the observability platform and
  recognize it instantly as *their* network.
- The map reflects the **real hierarchy** — edge/router at the top, switching layers in the middle,
  access points and end devices at the leaves.
- The customer can see **how things are connected**, down to which port on each device a cable uses.
- Devices that are physically or logically **grouped** (a switch stack, a chassis and its modules)
  appear as a single, expandable unit — not scattered.
- The customer can **filter and search** the map by the attributes they care about (site, role,
  VLAN, model, status).
- The map is **always current** — it reflects what the network looks like now, not last quarter.

### Non-Goals

- Not changing or controlling the network (read-only; observability and export only).
- Not replacing the customer's configuration or provisioning tooling.
- Not defining alerting, SLOs, or golden metrics here — only the topology experience.
- Not prescribing the rendering technology or data model (engineering's decision; see §10).

## 4. What the Customer Wants to See

Described as the customer would describe it. (Layout intent — engineering chooses how to render it.)

### 4.1 A top-down map that matches the layers of the network

The customer reads their network from the top down and wants the map to do the same:

> **Router / firewall at the top → core switches → distribution switches → access switches →
> access points → end devices/clients at the bottom.**

- Each layer sits in its own horizontal band; higher layers are "above" the things that depend on them.
- When a layer doesn't exist in a given site (e.g., a small site with no core), the map should
  **close the gap** gracefully rather than leave an empty band — small and large sites should both
  look natural.
- A device should never appear above the thing it hangs off of.

### 4.2 Connections that show both ends, including the port

When two devices are connected, the customer wants to see the cable **and which port it uses on each
end** — e.g., "core switch port 1/0/1 connects to distribution switch port 2/0/24." Port-level detail
is essential for troubleshooting and change planning, so it must be available on every link (at least
on hover/selection, ideally inline when zoomed in).

Redundant or cross-links between peer devices should be visible too, and visually distinguishable
from the main "up the hierarchy" connections.

### 4.3 Grouped devices shown as one unit

Some things are physically several boxes but operate as one, and the customer thinks of them as one:

- A **switch stack** (several switches cabled into one logical switch) should appear as a **single
  unit** that can be expanded to see its members.
- A **modular chassis and its line cards** should appear as one device that can be expanded to see
  its cards, and each card expanded to see its ports.

Internal wiring that only exists to make the group work (e.g., stacking cables) should not clutter
the map.

### 4.4 Drill-down without losing the big picture

The customer wants to start at the whole-network view and progressively drill in — site → device →
card → port → connected device — collapsing detail they don't need. Large networks (many hundreds of
devices, thousands of ports) must stay legible.

### 4.5 Status and identity at a glance

Each thing on the map should show what it is (role/type), what it's called, and whether it's healthy,
so the customer can spot trouble without clicking into each node.

## 5. How the Customer Understands Their Network

The customer thinks about their network in terms of a few simple, intuitive relationships. The
platform must be able to represent **all** of these faithfully. Whether existing platform
relationship types cover them, or new ones are needed, is an engineering/platform decision (§10) —
but the customer's mental model below is the requirement.

### 5.1 The three relationships the customer has in mind

- **"Is part of / contains"** — one thing is physically a piece of another and can't exist without
  it. A port is part of a switch; a line card is part of a chassis; a device belongs to a site.
  *Test the customer applies: if you remove it from its parent, does it stop being a working thing
  on its own? If yes, it's a part.*
- **"Is connected to"** — two independent devices joined by a link (a cable or a wireless
  association). Neither owns the other; they're peers. This includes both up-the-hierarchy links and
  side-to-side redundant links.
- **"Manages / controls"** — one independent device controls another independent device. The active
  member of a stack controls the other members; a primary firewall controls its standby. Both still
  exist on their own, but one is in charge.

### 5.2 Parent, child, sibling — in the customer's words

- **Parent:** the thing one level up that either *contains* this thing or *is in charge of* it.
- **Child:** the thing one level down that is *part of* its parent or *controlled by* it. Everything
  has a single clear parent in the structure (a port belongs to one switch, a stack member to one
  controller).
- **Sibling:** things at the same level — either sharing a parent, or peers connected to each other
  with no one in charge. Redundant core switches are siblings.

### 5.3 Why this distinction matters to the customer

Getting these right is not pedantry — it's what makes the map *trustworthy*. If the platform shows a
switch as "part of" another switch when it's really just cabled to it, the customer can no longer
trust the map to answer "what's actually inside this device?" or "what happens if this one fails?"
The relationships are the difference between a pretty picture and a correct one.

> **Engineering note:** if the platform's existing relationship vocabulary can't express all three of
> these honestly (containment, connection, control) for network entities, that is a strong signal to
> engage the New Relic platform team about first-class network entity/relationship types — rather
> than forcing one concept to stand in for another. See Appendix C–D for what the prototype did here.

## 6. What the Customer Wants to Filter & Search By

A static picture isn't enough — the customer needs to slice the map. They expect to filter, search,
and group by the attributes that matter operationally. At minimum:

- **Where:** site / location / network.
- **What:** device role (router, core, distribution, access, AP, client), vendor, model.
- **Identity:** name, serial, management IP, MAC.
- **Logical segmentation:** VLAN / subnet.
- **Connectivity:** which port, link speed, link type (uplink, access, trunk, wireless), and the
  device/port on the far end of each link.
- **Grouping membership:** which stack a switch belongs to and its role (active vs member); which
  chassis a card or port belongs to.
- **Health:** operational/administrative status.

Whatever the underlying representation, every entity (device, port, card, stack, site, VLAN) must
carry enough descriptive metadata that the customer can answer questions like *"show me all access
switches in the London site on VLAN 30 that are degraded"* without leaving the map. The customer
shouldn't have to know how the data is stored — they just expect to filter by these things.

## 7. Freshness & Trust

To the customer, a topology map is only useful if they can trust it reflects reality **now**:

- When a device or link is added, moved, or removed, the map should reflect it on the next refresh —
  no stale devices lingering, no missing new ones.
- When a device goes down, its status should change on the map; it shouldn't silently disappear or
  falsely appear healthy.
- The customer should have a sense of **how fresh** the data is (e.g., "last updated X minutes ago").
- The map must not show ghost connections or merged/duplicated devices. Correctness of *what connects
  to what* is more important than visual polish.

A map the customer catches being wrong once is a map they stop trusting. Freshness and correctness
are first-class requirements, not nice-to-haves.

## 8. Constraints

These hold regardless of how it's built:

- **Read-only from the network and vendor APIs.** The platform observes and exports; it never writes
  back to Meraki or any vendor system.
- **Lives inside the observability platform.** The experience should be where the customer already
  works, not a separate destination.
- **Scales to real networks.** Hundreds of devices and thousands of ports per customer must remain
  legible and performant.
- **No dependence on the customer hand-maintaining the diagram.** The topology is derived from
  discovery, not drawn by hand.

## 9. Success Criteria

We've met the customer's need when:

1. A network operator opens the topology view and, without training, recognizes their network and
   its layered structure.
2. They can trace any connection end-to-end, including the port on each side.
3. Stacks and modular chassis show as single, expandable units.
4. They can filter the map to a site, role, VLAN, or status and get a clean sub-view.
5. The map reflects a real change in the network within one refresh cycle, and never shows a
   connection or grouping that isn't real.
6. Anyone querying the underlying data (not just the picture) gets an accurate description of the
   network — the structure is correct in the data, not faked for the rendering.

## 10. A Note to Engineering

You own the "how." This section sets expectations, not implementation.

- **Use whatever delivers the outcomes.** If existing platform entities, relationships, and rendering
  surfaces can satisfy §4–§9 honestly, great. If they can't, that's not a reason to compromise the
  customer experience — it's a reason to escalate.
- **Engage the New Relic platform team when the primitives don't fit.** Network topology may warrant
  **first-class entity and relationship types** (e.g., a true "network device," "port," "stack," and
  native containment/connection/management relationships with topology-aware rendering). Treat
  building these — in partnership with the platform team — as a legitimate, expected option, not a
  last resort.
- **Do not fake structure to satisfy the renderer.** The customer (and anyone querying the data)
  must get a truthful model (§5.3, §9.6). If a rendering surface can only show hierarchy by
  misrepresenting relationships, prefer a surface you control, or push the platform team for proper
  support — don't corrupt the data.
- **Reuse the prototype where it helps.** The Appendix documents a working prototype, the lessons
  from it, and concrete recommendations (including a model that worked with today's primitives and
  the open questions that remain). Use it as a head start, and as evidence when making the case to
  the platform team — but the body of this PRD, not the Appendix, is the requirement.

Where you land on these choices, write it up so product and the platform team can see the tradeoffs.

---

# Appendix — Prior Project: What We Built & Recommend

_Reference material from the internal prototype. Informative, not normative. The full prototype-era
spec (which assumed today's New Relic primitives) is preserved at_
[`docs/topology-prd.md`](topology-prd.md).

## A. Context — what the prototype did

An internal project built a working topology web UI from Meraki/SNMP discovery (router/firewall →
switches → APs → clients, with switch stacks folded into single nodes) and then attempted to
reproduce that experience inside New Relic by pushing custom entities and user-defined relationships
via NerdGraph. The web UI met the §4 experience; reproducing it in New Relic surfaced the lessons in
B–F below.

## B. Key learnings

- **The web UI looks right because it controls its own layout.** The good hierarchy is a property of
  a renderer we own, not of the data.
- **New Relic's native entity map cannot be styled.** It auto-lays-out; the only lever over its
  shape is containment nesting. So the native map won't match the web UI without distorting the data.
- **The prototype faked hierarchy** by overloading the "contains" relationship onto switch-to-switch
  uplinks (a spanning-tree guess). This is the dishonest shortcut we want to avoid.
- **Relationship type must follow meaning, not rendering.** Choosing a type to trick the layout
  corrupts the data for anyone querying it.
- **User-defined relationships persist; auto relationships expire** (≈75 min TTL). Topology
  relationships should be explicit and reconciled (created and deleted) on each sweep.

## C. Recommended entity & relationship mapping (with today's primitives)

The prototype's rule for choosing a relationship — **"can it exist on its own?"**:

- Physically part of the parent, can't exist alone → **containment** (`CONTAINS`).
- A separate device the parent controls → **management** (`MANAGES`).
- Cabled peers, no one in charge → **connection** (`CONNECTS_TO`).

Cheat-sheet the prototype landed on (maps the §5 mental model onto current NR types):

| Customer concept | Pair | NR type used |
|---|---|---|
| part of | Site → device; chassis → line card; switch/card → port; port → AP | `CONTAINS` |
| connected to | switch ↔ switch (uplink & lateral); client ↔ AP | `CONNECTS_TO` |
| manages | stack active → members; primary firewall → secondary | `MANAGES` |

## D. Approaches we rejected

- **`CALLS`** (service-to-service / APM semantics) — wrong meaning for network gear, and our devices
  are custom Kentik/Meraki entity types, not service entities; likely rejected and pollutes APM views.
- **`IS`** (same real-world thing) — would merge a primary/secondary pair into one entity. Never use
  for distinct devices.
- **Overloading `CONTAINS` on uplinks** — the layout hack; abandoned. Uplinks are connections.

## E. Recommended architecture

Separate the **data** from the **picture**:

- **Data layer:** an honest entity/relationship model in New Relic (containment / connection /
  management), queryable and trustworthy — nothing shaped to please a renderer.
- **Presentation layer:** render the controlled, tiered, grouped layout in a **surface we own** (a
  topology nerdlet that can reuse the web UI's layout logic), since the native map can't be styled.
  This is consistent with the existing config nerdpack in the repo.

> This is the prototype's recommendation **given today's primitives**. If the platform team builds
> first-class network topology entities/relationships with topology-aware rendering (see §10), some
> of this separation may no longer be necessary — which is exactly the kind of tradeoff worth raising.

## F. Verification & open technical questions

- **`MANAGES` support is unverified** for these custom entity types via the user-defined mutation
  (`CONTAINS`/`CONNECTS_TO` are proven). Confirm against the NerdGraph schema; a read-only probe that
  attempts one `MANAGES` relationship and reports acceptance is the cheapest check. Fallback if
  unsupported: containment for stacks + a tag-only marker for HA pairs.
- **Tier assignment in flat (Meraki) networks** — how to assign role/tier when there's no true core
  or distribution layer (by uplink depth, model, or explicit tag).
- **Where edge/port detail lives** — on relationship attributes, on port entities, or both.
- **Scale targets** — confirm the largest expected device/port counts to size the renderer.

## G. Existing code references

- Tier ranks, stack folding, AP-to-parent mapping — [`ui/src/utils/layoutEngine.ts`](../ui/src/utils/layoutEngine.ts)
- Tier positions and core-collapse behavior — [`ui/src/components/HybridView.tsx`](../ui/src/components/HybridView.tsx)
- Device/link types — [`ui/src/types/topology.ts`](../ui/src/types/topology.ts)
- Entity push + event types/tags — [`nr_ingest/push_all_devices.py`](../nr_ingest/push_all_devices.py)
- Relationship create/delete via NerdGraph — [`nr_ingest/create_relationships.py`](../nr_ingest/create_relationships.py)
- NR entity/relationship reference — [`docs/reference/new-relic-entity-types.md`](reference/new-relic-entity-types.md)
- Map freshness behavior — [`docs/nr-ingest-status.md`](nr-ingest-status.md)
- Full prototype-era spec (assumes today's primitives) — [`docs/topology-prd.md`](topology-prd.md)
