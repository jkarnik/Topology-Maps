# New Relic Entities — Quick Reference

> **Source:** <https://docs.newrelic.com/docs/new-relic-solutions/new-relic-one/core-concepts/what-entity-new-relic/#types-definition>
> Captured 2026-06-18. New Relic docs change; re-check the source for authoritative detail.

## What's an entity?

An entity is anything that **(a)** reports data to New Relic (or contains data New Relic can access) **and (b)** has been given a unique entity ID. For most entities that ID is the `entityGuid` attribute.

An entity can be a fundamental data-reporting component (an application, a host, a database service) **or** a larger grouping of components. Example: aggregating hosts into a **workload** (a custom grouping) — the workload is itself an entity.

The **relationships between entities** are equally important. New Relic infers how entities connect and affect each other, surfacing business-relevant insight instead of a raw stream of monitored services.

- The **All entities** page (one.newrelic.com landing page) gives an overview of monitored entities.
- The **entity filter bar** (entity list, APM, browser, infra UIs) lets you explore and save filters.

## Entity identity & metadata

- Every entity has a New Relic ID reported as the `entityGuid` attribute. You can run NRQL queries using the GUID.
- In the UI: from any entity list, click an entity's icon → **See metadata & tags** to find the GUID and metadata.

## Entity definition files (domain + type)

Technical details for each entity type live in New Relic's GitHub repo for entity types. Each entity has files governing how it reports data (e.g. `golden_metrics.yml` for its most important metrics). An entity's **definition file** contains:

| Field | Meaning | Example |
|-------|---------|---------|
| **domain** | High-level category the entity belongs to | `APM`, `INFRA` |
| **type** | Specific entity type within the domain | `Application`, `AWSECSCONTAINERINSTANCE` |
| **Default tags** | Tags applied to the entity by default | — |
| **entityExpirationTime** | Time-to-live for the entity record | see below |

## Entity expiration (TTL)

`entityExpirationTime` governs how long the **record** of an entity persists after it stops reporting. (This is about the entity record, **not** telemetry data — telemetry retention is separate and governed by data retention settings / NRDB.)

| Value | Duration |
|-------|----------|
| `FOUR_HOURS` | 4 hours |
| `DAILY` | 24 hours |
| `EIGHT_DAYS` | **Default** if no deadline is defined |
| `QUARTERLY` | 3 months |
| `MANUAL` | Only for entities whose lifecycle is manually controlled (e.g. workloads, dashboards) |

Short-lived entities (e.g. Kubernetes containers) make regular expiration of stale records necessary.

## Grouping & organizing entities

- **Tag entities** for business-meaningful organization.
- **Create workloads** to group business-important sets of entities (team, department, service, data center, etc.).

## Entity synthesis (creating your own entities)

For telemetry from sources not supported out of the box, you can propose a mapping. Once approved, any matching telemetry is synthesized into an entity. Work is done in New Relic's entity-synthesis GitHub repo.

### Reserved attributes for synthesized entities

These are meant to be **synthesized** from received telemetry — do **not** set them manually unless you understand the consequences (doing so can cause missing entities or mis-associated telemetry).

| Attribute | Notes |
|-----------|-------|
| `entity.guid` | Generally don't set on telemetry. If present, NR won't change it. Use case: associating ingested telemetry with an already-monitored entity (overrides NR's entity identification). |
| `entity.name` | Don't set unless overriding the auto-selected entity name. Many entities use name as part of identity — changing it may generate a new entity. |
| `entity.type` | Avoid except certain legacy cases. May interfere with entity detection; existing definitions have overlapping values. Prefer other fields for query-time filtering. |

## Uninstrumented entities

From telemetry, New Relic can detect entities used by your app but not currently instrumented (e.g. an Amazon RDS database your instrumented service calls). NR creates an "uninstrumented entity" plus the relationship, shows it in the service map, and provides instructions to instrument it.

## Entity relationships

Connections are created automatically from inferred telemetry (e.g. two HTTP-communicating instrumented services → a calls/called-by relationship). View them via **Related entities** (right pane in entity explorer, Navigator, Lookout), service maps, distributed tracing, or the NerdGraph API.

### Relationship types

| Type | Description |
|------|-------------|
| `BUILT_FROM` | Target entity contains the code for the source entity. |
| `CALLS` | One service/application calls another (upstream/downstream display). |
| `CONNECTS_TO` | Source has a connection to the target. |
| `CONSUMES` | Source consumes messages from a target Kafka topic / queue. |
| `CONTAINS` | Hierarchical / infrastructure containment (e.g. HOST contains a container). |
| `HOSTS` | Between an application/process and the system it runs on. |
| `IS` | Same thing captured as a separate entity by another telemetry source. |
| `MANAGES` | Source manages a target subsystem of the source. |
| `MEASURES` | Source is used to measure the target. |
| `PRODUCES` | Source produces messages to a target Kafka topic / queue. |
| `SERVES` | Between a backend app and the browser app it returns in the response. |

### Automatically created relationships

Auto relationships have a **TTL** (default **75 minutes**; ranges from 10 minutes to 3 days by type) and are deleted if the underlying metrics stop reporting.

**Source: New Relic agent**

| Source | Type | Target | Why |
|--------|------|--------|-----|
| App (NR agent) | CALLS | App (NR agent) | Via `DurationByCaller` metric (reported by callee). |
| App (NR agent) | CALLS | Service (NR agent) | Caller reports `ExternalApp` metric when callee responds. |
| Service (NR agent) | CALLS | Service (NR agent) | Callee reports `ClientApplication` metric. |
| Service (NR agent) | CALLS | Datastore instance | Via `DatastoreInstance` metric (vendor/host/port). |
| APM agent | SERVES | Browser agent | APM agent injects browser agent into a page. |
| Workload entity | CONTAINS | Any entity | Created/updated with the workload; dynamic (tag-based) workloads re-create relationships every 5 min. |

**Source: Infrastructure**

| Source | Type | Target | Why |
|--------|------|--------|-----|
| Infra host | HOSTS | Application | App runs on host(s) running the infra agent. |
| Infra host | HOSTS | Container | Containers run on host(s) running the infra agent. |

**Source: Synthetic monitor**

| Source | Type | Target | Why |
|--------|------|--------|-----|
| Synthetic monitor | CALLS | Browser agent | Monitor checks a page with the browser agent. |
| Synthetic monitor | CALLS | APM application | Agent events with `nr.syntheticsMonitorId` link monitor → app. |

**Source: Kubernetes**

| Source | Type | Target |
|--------|------|--------|
| Cluster | CONTAINS | Pod / Deployment / DaemonSet / StatefulSet / Host |
| Deployment | CONTAINS | Pod |
| DaemonSet | CONTAINS | Pod |
| StatefulSet | CONTAINS | Pod |
| Pod | CONTAINS | Container |
| Host | HOSTS | Pod |
| Container | HOSTS | Application |

(All require the cluster to be instrumented with the New Relic Kubernetes integration.)

**External services**

| Source | Type | Target | Why |
|--------|------|--------|-----|
| External service | CALLS | External service | Span reports `service.name` + `parent.service.name`. |
| Application | IS | External service | Lets users navigate between them via Related entities. |
| Browser app (NR agent) | CALLS | External service | Via `Ajax/HostTransaction` metric on calling a URL. |
| Cluster | CONTAINS | External service | Span reports `k8s.cluster.name` matching the integration's cluster name. |
| Pod | HOSTS | External service | Span reports `service.name`, `k8s.cluster.name`, `k8s.pod.name`, `k8s.namespace.name`. |

### Legacy externals & exceptions

- A service invoked intermittently (>10 min between calls) may show as a **legacy external entity**, possibly duplicating an already-instrumented service.
- A service reached via multiple hostnames without tracing on each instance shows both instrumented and uninstrumented services — enable tracing on all instances to resolve.

### Custom entity relationships

When not auto-detected, create relationships manually via the NerdGraph API or the **Add/edit related entities** link in the UI. Currently only **calls/called-by** relationships between **service** entities can be created manually. Requires modify/delete capabilities on entity relationships.
