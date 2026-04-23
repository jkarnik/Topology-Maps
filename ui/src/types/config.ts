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
