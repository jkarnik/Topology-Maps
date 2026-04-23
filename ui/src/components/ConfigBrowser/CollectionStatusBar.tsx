import React from 'react';
import type { ConfigOrg, ConfigStatus } from '../../types/config';

interface Props {
  orgs: ConfigOrg[];
  selectedOrgId: string | null;
  status: ConfigStatus | null;
  onOrgChange: (orgId: string) => void;
  onStartBaseline: () => void;
  onStartSweep: () => void;
}

function statusChip(state: string): { bg: string; label: string } {
  switch (state) {
    case 'complete':     return { bg: 'bg-green-500',  label: 'Synced' };
    case 'in_progress':  return { bg: 'bg-yellow-500', label: 'Syncing' };
    case 'running':      return { bg: 'bg-yellow-500', label: 'Running' };
    case 'failed':       return { bg: 'bg-red-500',    label: 'Failed' };
    default:             return { bg: 'bg-gray-400',   label: 'Never baselined' };
  }
}

export const CollectionStatusBar: React.FC<Props> = ({
  orgs, selectedOrgId, status, onOrgChange, onStartBaseline, onStartSweep,
}) => {
  const state = status?.active_sweep?.status ?? status?.baseline_state ?? 'none';
  const chip = statusChip(state);
  const baselineStarted = status?.baseline_state !== 'none';

  return (
    <div className="flex items-center gap-4 p-3 border-b bg-white">
      <label className="text-sm text-gray-700">Org:</label>
      <select
        value={selectedOrgId ?? ''}
        onChange={(e) => onOrgChange(e.target.value)}
        className="border rounded px-2 py-1 text-sm"
      >
        <option value="">Select an org…</option>
        {orgs.map((o) => (
          <option key={o.org_id} value={o.org_id}>
            {o.org_id} ({o.observation_count} observations)
          </option>
        ))}
      </select>

      <span className={`inline-flex items-center gap-2 px-2 py-1 rounded text-xs text-white ${chip.bg}`}>
        <span className="w-2 h-2 rounded-full bg-white/80" />
        {chip.label}
        {status?.last_sync && (
          <span className="ml-1 text-white/80">{new Date(status.last_sync).toLocaleString()}</span>
        )}
      </span>

      <div className="ml-auto flex gap-2">
        {!baselineStarted ? (
          <button
            className="px-3 py-1 text-sm rounded bg-blue-600 text-white hover:bg-blue-700"
            disabled={!selectedOrgId}
            onClick={onStartBaseline}
          >Start baseline</button>
        ) : (
          <button
            className="px-3 py-1 text-sm rounded bg-gray-700 text-white hover:bg-gray-800"
            disabled={!selectedOrgId || state === 'running'}
            onClick={onStartSweep}
          >Run full sweep</button>
        )}
      </div>
    </div>
  );
};
