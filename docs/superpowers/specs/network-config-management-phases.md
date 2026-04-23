# Network Configuration Management — 7-Phase Roadmap

**Source of truth:** this doc summarizes the full scope. Each phase has (or will have) its own design spec and implementation plan set.

## Cross-cutting constraints (all phases)

- **Observability, not automation.** The tool is positioned as a New Relic observability surface. It reads configs from vendor APIs (Meraki today, extensible later), analyzes them, and exposes them for human understanding. It **never writes configuration changes back to the source system.** Any feature that would otherwise mutate vendor state is delivered as an **exportable artifact** the user manually uploads via the vendor's own UI or CLI.
- **Change-log-driven wherever possible.** Vendor change-log APIs (e.g. Meraki's `/organizations/{id}/configurationChanges`) are the primary signal for incremental updates. Full polling is reserved for one-time baseline and weekly anti-drift sweeps.
- **Content-addressed storage.** Observations are deduplicated by SHA-256 of a canonical JSON form. This keeps storage flat even with years of history.
- **Secret redaction at ingestion.** No vendor secret (PSK, RADIUS shared secret, SNMP community string, VPN PSK, webhook shared secret) ever lands in the local SQLite DB in plaintext. Change detection still works via per-field hashes.

---

## Phase status

| # | Phase | Status | Ship date |
|---|---|---|---|
| 1 | Config Collection & Storage | ✅ Shipped | 2026-04-22 |
| 2 | Diff Engine & Change Timeline | 📋 Planned | — |
| 3 | Topology Overlay | 📋 Planned | — |
| 4 | Baseline & Drift Monitor | 📋 Planned | — |
| 5 | Compliance Rule Engine | 📋 Planned | — |
| 6 | Multi-Site & Template Comparison | 📋 Planned | — |
| 7 | Export & Revert Bundles | 📋 Planned | — |

---

## Phase 1 — Config Collection & Storage ✅

**Goal:** Continuously capture Meraki configuration state across organization, network, and device levels; redact secrets at ingestion; store observations in content-addressed SQLite; expose a tree-based browser.

**Scope delivered:**
- 55+ Tier 1+2 Meraki config endpoints with product-type filtering
- Change-log-driven incremental updates (every 30 min, configurable) + one-time baseline + weekly anti-drift sweep
- Content-addressed SQLite schema (`config_blobs`, `config_observations`, `config_change_events`, `config_sweep_runs`)
- Secret redaction with regex-guard test to catch new secret-bearing fields as Meraki evolves
- REST API (`/api/config/*`) + WebSocket progress channel (`/ws/config`)
- React UI: tree browser + JSON viewer + live progress overlay, dark theme matching the existing topology workspace
- Scales to 30K+ devices per org via rate-limited (5 req/sec) background workers

**Design spec:** [2026-04-22-config-collection-phase1-design.md](2026-04-22-config-collection-phase1-design.md)
**Plans:** [docs/superpowers/plans/2026-04-22-phase1-*.md](../plans/)

---

## Phase 2 — Diff Engine & Change Timeline

**Goal:** Make the data collected in Phase 1 actionable by letting users see what changed and when.

**Scope:**
- **Structural diff** between any two observations of the same `(entity, config_area, sub_key)`. Field-level, type-aware (list reordering vs. insertion, object key changes, value changes).
- **Change-log timeline** — chronological feed of admin-made changes across the org, filterable by entity, admin, date, config area. Uses the already-collected `config_change_events` table.
- **Rich renderers for high-value areas** — structured diff visualization for VLANs, firewall rules, SSIDs, switch ports (not just raw JSON with colors).
- **Secret-change marker** — when a `_hash` companion on a redacted field differs, show "Secret changed on <date>" without ever storing or displaying the plaintext.

**Depends on:** Phase 1 (storage, history endpoint, change events).

**Key API consumers:** `GET /api/config/entities/{type}/{id}/history`, `GET /api/config/change-events`.

---

## Phase 3 — Topology Overlay

**Goal:** The differentiating feature. Overlay config-change markers directly on the existing L2, L3, and Hybrid topology views so changes are visible in spatial context, not just a sidebar log.

**Scope:**
- **Change markers on topology nodes** — per-device dot/pulse indicating recent config change. Filterable by time window ("last 24h", "since last Friday").
- **Time-scrubber** — slider at the bottom of the topology view that "rewinds" the map to any point in the past, using observation history. Network had 40 devices on Jan 1st → scrub to that date → see 40.
- **Per-node click opens Phase 2 diff** — the topology becomes an entry point into the diff engine.
- **Color-coded by change type** — config change (amber), drift discrepancy (red), compliance fail (purple).

**Depends on:** Phase 2 (diff), Phase 4 (drift, for discrepancy markers — optional coupling).

---

## Phase 4 — Baseline & Drift Monitor

**Goal:** Let an operator pin "this is what good looks like" and get alerted when something deviates, independent of the change log.

**Scope:**
- **Pin any observation as a "golden" baseline** for an entity or config area.
- **Scheduled drift comparison** — computes diff between current observation and pinned baseline, writes drift score.
- **Drift dashboard** — all entities deviating from their baseline, sorted by severity (number of fields changed, secret changes weighted higher).
- **Drift attribution** — when a drift is detected, try to link it to a change-log event in the same time window. "The `psk` field changed on 2026-05-01 by alice@example.com" is more actionable than "something drifted."
- **Bulk baseline** — pin the current state of N networks as their baselines in one click (e.g., "accept current state of all stores as gold").

**Depends on:** Phase 1 (storage, observations), Phase 2 (diff).

---

## Phase 5 — Compliance Rule Engine

**Goal:** Enforce intent, not just detect change. "This is what we WANT to be true regardless of history."

**Scope:**
- **Declarative rule DSL** — e.g. `SSID.authMode == "8021x-radius" WHERE SSID.name CONTAINS "Corp"` or `port.stpGuard == "bpdu guard" WHERE port.portId matches "^[1-4]$"`.
- **Rule library** — prebuilt rules for PCI-DSS, common best practices, NIST guidelines. Per-rule metadata: severity, rationale, remediation hint.
- **Pass/fail dashboard** — per rule, per network, per device. Show which entities fail each rule, with the specific field(s) that caused the failure.
- **Custom rules** — customers write their own rules in YAML; stored server-side; evaluated on each observation.
- **Coexists with Phase 4** — drift is "did this change unexpectedly?", compliance is "should this ever be this way?" Orthogonal concerns, share the evaluation engine.

**Depends on:** Phase 1 (observations), Phase 2 (field-level introspection).

---

## Phase 6 — Multi-Site & Template Comparison

**Goal:** For customers with many similar networks (retail chains, branch offices), make "how does Store 42 differ from Store 7?" a first-class question.

**Scope:**
- **Template extraction** — save any config subtree (e.g., "standard retail SSID set", "standard switch access policy") as a local template. Stored in our DB, NOT pushed to Meraki config templates (which would mutate Meraki state).
- **Side-by-side network comparison** — pick two networks, show which config areas differ and by how much. Useful for "why is Store 42 getting different behavior than Store 7?"
- **Coverage dashboard** — which networks have which config areas populated. "45 / 50 stores have a guest SSID configured; here are the 5 missing."
- **Template diff-against-template** — score each network's deviation from a chosen template. Variant of Phase 4's drift but using a template as the reference instead of a pinned observation.

**Depends on:** Phase 1, Phase 2, Phase 4 (conceptually — drift engine reused with different reference).

---

## Phase 7 — Export & Revert Bundles

**Goal:** Close the loop for customers who want to use our data outside the tool — for backups, external VCS, audit trails, or manual rollback.

**Scope:**
- **Per-entity JSON export** — "download this observation" button on any config area card. Produces a single JSON file.
- **Per-network / per-org bundle export** — tarball or zip of all current configs, structured so it can be committed to git. Filenames and layout deterministic so two exports of the same state produce identical files (clean diffs in external tooling).
- **"Revert bundle" generator** — given a past observation, produce a Meraki-upload-ready artifact the user manually applies via Dashboard or the Meraki CLI. **The tool never writes to Meraki directly.** Format open question:
  - **Literal API shape** (`PUT /networks/{id}/appliance/vlans` body) — fastest to apply, tied to current Meraki API shape
  - **Portable YAML** — easier to version-control, requires translation at apply time
- **Scheduled git-sync** (optional) — push bundle exports to a customer-owned git repo on a schedule, giving a full external history independent of our SQLite DB.

**Depends on:** Phase 1 (storage + blobs). Phase 2's diff engine is optional but useful for generating "minimal patch" revert bundles instead of full snapshots.

---

## Open questions across the roadmap

1. **Phase 2 diff: SSID-enabled edge case** — how does the diff view render "SSID enabled = false → true" when the reactive catch simultaneously pulls sub-endpoints for the first time? Candidates: show the full enable-time config as "initial state" with no diff, or retroactively synthesize an empty baseline and diff against it.
2. **Phase 4 drift attribution** — when an entity drifts from its golden snapshot, should the UI preferentially show the originating change-log event (if any) as the "reason" for the drift, or treat drift as a separate orthogonal signal?
3. **Phase 7 export format** — literal API-shape vs. portable YAML. Depends on user research: are the primary consumers ops teams who want to replay into Dashboard, or compliance/audit teams who want long-term archival?
4. **Change-event retention policy** — Meraki keeps 31 days. Should we extend retention indefinitely in our own store, or enforce a matching 31-day ceiling? Impacts compliance posture and storage footprint. Phase 4 and Phase 5 both benefit from long retention; Phase 2's timeline gets most of its value from the trailing 30 days.
5. **Phase 3 time-scrubber fidelity** — observations are per-(entity, area), not global snapshots. A "topology as of Tuesday 3pm" view has to reconstruct per-node state from many independent observation histories. Edge cases: a device that was added Tuesday 4pm — does it appear on the 3pm view or not? (Presumably no, but the UX needs to be clear.)
6. **Non-Meraki vendors** — the architecture is vendor-neutral in principle (redactor, storage, endpoints-catalog abstractions), but every concrete piece today is Meraki-specific. Adding Fortinet or Cisco IOS-XE would require a new client module + new catalog. Expected as a Phase 8+ or as parallel work.
