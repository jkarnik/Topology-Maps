# PRD: Network Topology in the Observability Platform

> **Status:** Draft for engineering review
> **Author:** Product
> **Date:** 2026-06-29
> **Audience:** Engineering team (and, where needed, the New Relic platform team)

This PRD describes **what the customer wants** from network topology inside their observability
platform — stated from first principles, in terms of outcomes and desired experience, **not**
implementation. *How* to deliver it is engineering's call: with existing platform primitives, or by
partnering with the New Relic platform team to introduce new kinds of entities and relationships
where today's primitives don't fit.

Topology serves **two equally important purposes** (see §1):

1. **A map the customer can see and trust** — understand their network at a glance.
2. **The dependency graph that powers alert correlation and noise suppression** — so a single
   failure produces a single root-cause incident, not an alert storm.

Both depend on the same underlying model being correct.

---

## 1. Purpose & Framing

Network topology in the observability platform exists to serve two purposes that matter equally.

### Purpose 1 — See and understand the network

The customer wants to understand their physical and logical network at a glance, inside the same
platform where they already watch performance and health: the layered hierarchy, what connects to
what, grouped devices, all current and trustworthy.

### Purpose 2 — Power alert correlation & noise suppression

The same topology is the **dependency graph** New Relic's correlation engine uses to make sense of
failures. When a switch goes down, every access point and device beneath it goes down too — which on
its own would create an **alert storm** of dozens of independent alerts. With topology, the engine
recognizes that the switch is the **root cause**, raises a **single incident** for it, **groups** the
downstream alerts inside that incident, and attributes the root cause correctly. The customer sees
one actionable problem instead of fifty symptoms.

These purposes reinforce each other: both require the relationships between devices to be modeled
**correctly and directionally** (what depends on what), not just drawn. A model good enough to
correlate failures is also the model that renders an honest map.

**Division of responsibility:**

- **Product owns the "what":** the experience, the customer's mental model, the outcomes below.
- **Engineering owns the "how":** data modeling, rendering, and platform choices. Engineering
  decides whether existing entity/relationship primitives are sufficient, or whether to work with
  the **New Relic platform team to define new kinds of entities and relationships** purpose-built
  for network topology. Either path is acceptable as long as the customer outcomes are met.

Nothing in this document should be read as prescribing a specific entity type, relationship type,
API, rendering surface, or correlation algorithm. It defines the customer's requirements; the
technical choices are engineering's (§10).

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
- **A single failure buries them in alerts.** When a switch fails, every access point and device
  beneath it alarms at once. The customer gets dozens of simultaneous alerts with no indication that
  they share one cause — so they chase symptoms instead of fixing the switch.
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

**Correlation outcomes:**

- When one device fails and takes others down with it, the customer gets **one incident** for the
  root cause, with the downstream alerts **grouped inside it** — not an alert storm.
- The incident **names the real root cause** (the failed switch), not a random symptom.
- Genuinely independent failures still surface as their own incidents — the engine suppresses noise,
  not signal.

### Non-Goals

- Not changing or controlling the network (read-only; observability and export only).
- Not replacing the customer's configuration or provisioning tooling.
- Not defining the customer's alert conditions, thresholds, or SLOs — this PRD covers how topology
  **feeds** correlation, not which alerts exist or how they're configured.
- Not prescribing the rendering technology, correlation algorithm, or data model (engineering's
  decision; see §10).

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

Internal wiring that only exists to make the group work (e.g., stacking cables between members)
should be **hidden while the group is collapsed**, so the default view stays clean — but **visible
when the customer explodes/expands the group**. Exploding a stack should reveal the member chassis
*and* the stacking links between them; the detail is there when wanted, out of the way when not.

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

### 5.2 Sites are the top-level container

Every device — and everything inside it — lives within a **site** (a location / network). The site
is itself an entity, the root of that location's hierarchy, not just a label or a filter. The
customer navigates site-first: choose a site, then see its devices and how they're structured
beneath it. A device belongs to exactly one site.

## 6. Alert Correlation & Noise Suppression

This is the second purpose, and it depends entirely on the relationships in §5 being correct and
directional. The topology **is** the dependency graph the correlation engine reasons over.

### 6.1 The outcome the customer wants

When one failure causes many alerts, the customer should get **one incident** for the underlying
cause, with the dependent alerts grouped inside it — instead of a storm of equal-looking alerts.

> **Concretely:** a core switch fails. Every access point and downstream device that reaches the
> network only through that switch stops reporting and alarms. Instead of ~50 separate incidents, the
> customer gets **one incident — "Core switch X down"** — with the 50 downstream alerts grouped under
> it, and the switch correctly named as the root cause.

### 6.2 How failure should propagate through the topology

The relationships in §5 are **directional**: they encode which thing depends on which. The customer's
mental rule, which the engine should follow:

- **Dependency flows downward.** A child depends on its parent (a port on its switch, an AP on its
  port, a contained device on its container). A downstream device depends on the upstream device(s)
  that connect it toward the core.
- **A parent failing makes its dependents "expected to fail."** If a switch is down, the ports, cards,
  APs, and downstream devices that depend on it are expected to be unreachable. Their alerts are
  **symptoms**, not separate problems.
- **The root cause is the highest-up entity whose own failure explains the rest.** The incident is
  attributed to it; the dependent (downstream) alerts are suppressed into that one incident rather
  than raised on their own.
- **Redundancy stops the propagation.** If a dependent device has another *working* path to the core
  (a redundant uplink, a sibling/second connection), it is **not** expected to fail — so its alert
  must **not** be suppressed. Over-suppression that hides a real second failure is as bad as the storm.
- **Independent failures stay independent.** Two unrelated devices failing at the same time, with no
  dependency between them, should remain two incidents. The engine suppresses noise, never signal.

### 6.3 What this requires of the model

For the engine to do the above, the topology must provide:

- **Directional relationships** — every dependency edge knows which side is the depended-upon
  (upstream/parent) and which is the dependent (downstream/child). Adjacency alone is not enough.
- **Redundant paths represented** — when a device has more than one way to reach the core, all paths
  exist in the model so the engine can tell "still reachable" from "isolated."
- **A health signal per entity** the engine can read to know what's actually alarming.

### 6.4 Worked example

```
Core switch X  ── down ──▶ root cause, ONE incident: "Core switch X down"
   ├─ AP-1 .. AP-20  (reach the network only via X)         → expected down → grouped, suppressed
   ├─ Access switch Y (single uplink to X)                  → expected down → grouped, suppressed
   │     └─ its clients                                      → expected down → grouped, suppressed
   └─ Access switch Z (redundant uplink to core switch X2)  → still reachable → NOT suppressed
```

Without topology, this is 20+ equal incidents and no root cause. With it, it's one incident, correct
cause, and switch Z's situation (if it *does* have a problem) is still visible.

### 6.5 Engineering owns the mechanism

This section defines the **behavior** the customer needs, not the algorithm. Whether it's delivered
by New Relic's existing correlation/incident-intelligence capabilities reading these relationships, or
needs new platform support, is engineering's call (§10) — provided the propagation behavior in §6.2
holds.

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
3. Stacks and modular chassis show as single, expandable units, and exploding them reveals members
   and their internal links.
4. The map reflects a real change in the network within one refresh cycle, and never shows a
   connection or grouping that isn't real.
5. Anyone querying the underlying data (not just the picture) gets an accurate description of the
   network — the structure is correct in the data, not faked for the rendering.
6. **When a device fails and takes its dependents down, the customer gets one incident naming the
   root cause, with the downstream alerts grouped inside it** — not a storm of equal alerts.
7. **A dependent device that still has a working (redundant) path is not swept into the suppression**,
   and genuinely independent failures remain separate incidents.

## 10. A Note to Engineering

You own the "how." This section sets expectations, not implementation.

- **Use whatever delivers the outcomes.** If existing platform entities, relationships, rendering
  surfaces, and correlation capabilities can satisfy §4–§9 honestly, great. If they can't, that's not
  a reason to compromise the customer experience — it's a reason to escalate.
- **Engage the New Relic platform team when the primitives don't fit.** Network topology may warrant
  **first-class entity and relationship types** (e.g., a true "network device," "port," "stack," and
  native, directional containment/connection/management relationships with topology-aware rendering
  *and* correlation support). Treat building these — in partnership with the platform team — as a
  legitimate, expected option, not a last resort.
- **Do not fake structure to satisfy the renderer.** The customer, anyone querying the data, **and the
  correlation engine** must get a truthful, directional model (§5, §6.3). If a rendering surface can
  only show hierarchy by misrepresenting relationships, prefer a surface you control, or push the
  platform team for proper support — don't corrupt the data. A faked relationship doesn't just
  mislead the map; it produces wrong root-cause correlation.

Where you land on these choices, write it up so product and the platform team can see the tradeoffs.

