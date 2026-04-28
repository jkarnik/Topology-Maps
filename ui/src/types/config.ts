// Types matching /api/config/* responses (Plan 1.19)

export type BaselineState = 'none' | 'in_progress' | 'complete' | 'failed';
export type EntityType = 'org' | 'network' | 'device' | 'ssid';
export type SourceEvent =
  | 'baseline'
  | 'change_log'
  | 'anti_drift_confirm'
  | 'anti_drift_discrepancy'
  | 'manual_refresh';

export interface ConfigOrg {
  org_id: string;
  name: string | null;
  observation_count: number;
  baseline_state: BaselineState;
  last_baseline_at: string | null;
  active_sweep_run_id: number | null;
}

export interface ConfigStatus {
  baseline_state: BaselineState;
  last_sync: string | null;
  active_sweep: { id: number; kind: string; status: string } | null;
}

export interface ConfigObservation {
  id: number;
  org_id: string;
  entity_type: EntityType;
  entity_id: string;
  config_area: string;
  sub_key: string | null;
  hash: string;
  observed_at: string;
  source_event: SourceEvent;
  change_event_id: number | null;
  sweep_run_id: number | null;
  name_hint: string | null;
  enabled_hint: 0 | 1 | null;
}

export interface ConfigArea extends ConfigObservation {
  payload: unknown;
}

export interface ConfigEntity {
  entity_type: EntityType;
  entity_id: string;
  org_id: string;
  areas: ConfigArea[];
}

export interface ConfigTreeNetwork {
  id: string;
  name: string | null;
  config_areas: string[];
  devices: { serial: string; name: string | null }[];
  ssids: { id: string; name: string | null }[];
}

export interface ConfigTree {
  org: { id: string; config_areas: string[] };
  networks: ConfigTreeNetwork[];
}

export interface ConfigChangeEvent {
  id: number;
  org_id: string;
  ts: string;
  admin_id: string | null;
  admin_name: string | null;
  admin_email: string | null;
  network_id: string | null;
  network_name: string | null;
  ssid_number: number | null;
  ssid_name: string | null;
  page: string | null;
  label: string | null;
  old_value: string | null;
  new_value: string | null;
}

export type ConfigWsEvent =
  | { type: 'sweep.started'; sweep_run_id: number; org_id: string; kind: string; total_calls: number }
  | { type: 'sweep.progress'; sweep_run_id: number; completed_calls: number; total_calls: number }
  | { type: 'sweep.completed'; sweep_run_id: number; org_id: string }
  | { type: 'sweep.failed'; sweep_run_id: number; org_id: string; error_summary: string }
  | { type: 'observation.updated'; org_id: string; entity_type: string; entity_id: string; config_area: string }
  | { type: 'change_event.new'; org_id: string; event_id: number; network_id: string | null; label: string | null; ts: string };

// ── Diff types ────────────────────────────────────────────────────────────────

export type DiffChangeType =
  | { type: 'FieldChanged'; key: string; before: unknown; after: unknown }
  | { type: 'FieldAdded';   key: string; value: unknown }
  | { type: 'FieldRemoved'; key: string; value: unknown }
  | { type: 'SecretChanged'; key: string }
  | { type: 'RowAdded';    identity: unknown; row: Record<string, unknown> }
  | { type: 'RowRemoved';  identity: unknown; row: Record<string, unknown> }
  | { type: 'RowChanged';  identity: unknown; field_changes: DiffChangeType[] }

export interface DiffResult {
  shape: 'object' | 'array'
  changes: DiffChangeType[]
  unchanged_count: number
}

export interface OrgDiffResultItem {
  entity_type: string
  entity_id: string
  config_area: string
  sub_key: string
  name_hint: string
  to_observed_at: string
  diff: DiffResult
}

export interface OrgDiffResponse {
  from_ts: string
  to_ts: string
  total_entities_checked: number
  changed_count: number
  results: OrgDiffResultItem[]
}

export interface TimelineEntry {
  config_area: string
  sub_key: string
  observed_at: string
  source_event: string
  hash: string
  has_diff: boolean
  prior_hash: string | null
  admin_email: string | null
}

export interface EntityTimelineResponse {
  entity_type: string
  entity_id: string
  entries: TimelineEntry[]
}

// ── Phase 6: Multi-Site Comparison ───────────────────────────────────────────

export interface NetworkCompareArea {
  config_area: string
  sub_key: string | null
  status: 'differs' | 'identical' | 'only_in_a' | 'only_in_b'
  diff: DiffResult | null
}

export interface NetworkCompareResponse {
  network_a: { id: string; name: string | null }
  network_b: { id: string; name: string | null }
  areas: NetworkCompareArea[]
  total_areas: number
  differing_areas: number
  total_changes: number
}

export interface CoverageArea {
  config_area: string
  network_count: number
  network_total: number
  missing_networks: { id: string; name: string | null }[]
  device_breakdown: { id: string; name: string | null }[]
}

export interface CoverageResponse {
  areas: CoverageArea[]
}

export interface TemplateAreaRef {
  config_area: string
  sub_key: string | null
  blob_hash: string
}

export interface ConfigTemplate {
  id: number
  org_id: string
  name: string
  source_network_id: string
  source_network_name: string | null
  created_at: string
  areas: TemplateAreaRef[]
}

export interface TemplateAreaScore {
  config_area: string
  score_pct: number
  change_count: number
}

export interface NetworkTemplateScore {
  network_id: string
  network_name: string
  score_pct: number
  change_count: number
  total_fields: number
  missing_areas: string[]
  area_scores: TemplateAreaScore[]
}

export interface TemplateScoresResponse {
  template: { id: number; name: string; area_count: number }
  scores: NetworkTemplateScore[]
}
