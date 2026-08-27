# Work Request Draft — Network Topology Backend/Maps Engineering

> Draft content for a Jira **Work Request** ticket, ready to paste into the `[XD-Ops] Quarterly planning` board (or the equivalent board this team tracks Work Requests on). No Jira integration is connected in this session, so this file is the source to copy from — it isn't submitted automatically.

## Summary
Build the topology data model and discovery pipeline to support network topology mapping and alert correlation in the observability platform

## Description

**Why is this important?**
The topology feature has two dependents that both need a correct backend model: a map the customer can trust, and the dependency graph New Relic's correlation engine uses to turn an alert storm (e.g. 50 alerts when one switch fails) into a single root-cause incident. Both fail if the underlying relationships aren't modeled correctly and directionally — a model good enough to correlate failures is also the model that renders an honest map. Full detail: [`docs/topology-prd-customer-first.md`](topology-prd-customer-first.md).

**What are the desired outputs and outcomes?**
Backend/data-model deliverables covering the engineering scope defined in the PRD (§5, §6, §7, §8, §10):
- **Entity model** — site as a first-class entity (root of its location's hierarchy) containing devices; devices independently real and belonging to exactly one site.
- **Directional relationship model** covering all four customer relationships: *contains* (site → device), *is part of* (port/line-card → parent device, non-functional standalone), *is connected to* (peer devices/ports, cabled or wireless), *manages/controls* (stack active member → members, primary → standby). Every dependency edge must know which side is upstream/parent vs. downstream/child — adjacency alone isn't sufficient.
- **Redundant-path representation** — when a device has more than one path to the core, all paths must exist in the model so the correlation engine (or its consumer) can distinguish "still reachable" from "isolated," per the worked example in PRD §6.4.
- **Per-entity health signal** the correlation mechanism can read.
- **Discovery/freshness pipeline** — topology reflects adds/moves/removals on the next refresh cycle, with no ghost connections, no merged/duplicated devices, and a visible "data as of" freshness signal.
- **Grouped-device modeling** — switch stacks and modular chassis represented so downstream dependents attach to the group, not a specific member (stack fails as a unit; only losing the whole stack propagates downstream).
- **Scale target** — hundreds of devices, thousands of ports per customer, without degrading collection or query performance.
- **Read-only constraint** — no writes back to Meraki or any vendor API; discovery/export only.
- **Platform primitive decision** — assess whether existing New Relic entity/relationship primitives satisfy the above, or whether new first-class types (network device, port, stack, directional containment/connection/management relationships) are needed; if new primitives are needed, engage the New Relic platform team rather than faking structure to fit existing renderers/correlation.

Definition of done: a topology data model and discovery/collector implementation that (a) a query against the underlying data returns an accurate, non-faked description of the network per PRD §9.5, and (b) supports the failure-propagation behavior in PRD §6.2 (root cause identified, dependents suppressed, redundant paths not suppressed, independent failures stay independent) — either directly or by way of a documented handoff to the New Relic platform team, with tradeoffs written up per PRD §10.

**Where should we track our work?**
PRD: [`docs/topology-prd-customer-first.md`](topology-prd-customer-first.md) — link the relevant initiative ticket here once created, with issue link `blocks`. Recommend linking this ticket to the UX design Work Request ([`docs/wr-topology-ux-design-support.md`](wr-topology-ux-design-support.md)) as a related/dependent item, since the design deliverables consume this data model.

**When is the work needed?**
FY27Q3 (due date within the quarter — to be finalized during planning negotiation).

**Who's requesting the work and which area do they belong to?**
Requested by Product. Point of contact: Jay Karnik (PM). Relevant stakeholders: XD/Design team (consumes this model for the map — see the paired design WR), and the New Relic platform team (required if new entity/relationship primitives are needed per PRD §10).

## Jira Fields

| Field | Value |
|---|---|
| Work Type | Work Request |
| Requesting parent group | Product |
| Team | Maps |
| Assignee | TBD (Maps team lead to assign) |
| Due date | TBD — within FY27Q3 |
| Linked issues | Link to initiative ticket ('blocks'); link to UX design WR as related |
| Reporter | Jay Karnik |
| Labels | FY27Q3 |
| Priority | P1 (Critical) |
| Story points | TBD — estimate during team triage |
