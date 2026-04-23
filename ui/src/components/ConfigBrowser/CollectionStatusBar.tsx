import React, { useState, useEffect } from 'react';
import type { ConfigOrg, ConfigStatus } from '../../types/config';
import type { SweepProgress } from '../../hooks/useConfigCollection';

interface Props {
  orgs: ConfigOrg[];
  selectedOrgId: string | null;
  status: ConfigStatus | null;
  sweepProgress: SweepProgress | null;
  onOrgChange: (orgId: string) => void;
  onStartBaseline: () => void;
  onStartSweep: () => void;
}

function statusChip(state: string): { color: string; label: string; dotGlow: string } {
  switch (state) {
    case 'complete':
      return { color: 'var(--accent-green)', label: 'Synced', dotGlow: 'rgba(0, 214, 143, 0.6)' };
    case 'in_progress':
    case 'running':
    case 'queued':
      return { color: 'var(--accent-cyan)', label: 'Syncing', dotGlow: 'rgba(0, 229, 200, 0.6)' };
    case 'failed':
      return { color: 'var(--accent-red)', label: 'Failed', dotGlow: 'rgba(255, 71, 87, 0.6)' };
    default:
      return { color: 'var(--text-muted)', label: 'Never baselined', dotGlow: 'rgba(85, 102, 119, 0.3)' };
  }
}

const MONO: React.CSSProperties = { fontFamily: "'JetBrains Mono', monospace" };

function useElapsed(startedAt: number | null): number {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (startedAt === null) { setElapsed(0); return; }
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => clearInterval(id);
  }, [startedAt]);
  return elapsed;
}

export const CollectionStatusBar: React.FC<Props> = ({
  orgs, selectedOrgId, status, sweepProgress, onOrgChange, onStartBaseline, onStartSweep,
}) => {
  const state = status?.active_sweep?.status ?? status?.baseline_state ?? 'none';
  const chip = statusChip(state);
  const hasBaselined = !!status && status.baseline_state !== 'none';

  const elapsed = useElapsed(sweepProgress?.startedAt ?? null);
  const pct = sweepProgress && sweepProgress.total > 0
    ? Math.min(99, Math.round((sweepProgress.completed / sweepProgress.total) * 100))
    : null;
  const secsRemaining = sweepProgress && elapsed > 2 && sweepProgress.completed > 0
    ? Math.max(0, Math.round((elapsed / sweepProgress.completed) * (sweepProgress.total - sweepProgress.completed)))
    : null;

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        padding: '10px 20px',
        background: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border-subtle)',
        ...MONO,
      }}
    >
      <label style={{ fontSize: '11px', color: 'var(--text-secondary)', letterSpacing: '0.06em' }}>
        Org:
      </label>
      <select
        value={selectedOrgId ?? ''}
        onChange={(e) => onOrgChange(e.target.value)}
        style={{
          background: 'var(--bg-tertiary)',
          color: 'var(--text-primary)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '5px',
          padding: '5px 10px',
          fontSize: '12px',
          ...MONO,
          minWidth: '220px',
          cursor: 'pointer',
        }}
      >
        <option value="">Select an org…</option>
        {orgs.map((o) => (
          <option key={o.org_id} value={o.org_id}>
            {o.name ? `${o.name} — ${o.observation_count} observations` : `${o.org_id} (${o.observation_count} observations)`}
          </option>
        ))}
      </select>

      {/* Status chip */}
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '7px',
          padding: '4px 10px',
          borderRadius: '5px',
          background: 'var(--bg-tertiary)',
          border: '1px solid var(--border-subtle)',
          fontSize: '11px',
          color: chip.color,
          letterSpacing: '0.06em',
        }}
      >
        <span
          style={{
            display: 'inline-block',
            width: '7px',
            height: '7px',
            borderRadius: '50%',
            background: chip.color,
            boxShadow: `0 0 5px ${chip.dotGlow}`,
          }}
        />
        <span style={{ fontWeight: 600 }}>{chip.label}</span>
        {pct !== null && (
          <>
            <span style={{ color: 'var(--text-muted)', fontWeight: 400, marginLeft: '4px' }}>
              {pct}%
            </span>
            {secsRemaining !== null && (
              <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>
                · {secsRemaining}s left
              </span>
            )}
          </>
        )}
        {pct === null && status?.last_sync && (
          <span style={{ color: 'var(--text-muted)', fontWeight: 400, marginLeft: '4px' }}>
            {new Date(status.last_sync).toLocaleString()}
          </span>
        )}
      </span>

      <div style={{ flex: 1 }} />

      {!hasBaselined ? (
        <button
          onClick={onStartBaseline}
          disabled={!selectedOrgId}
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: '11px',
            fontWeight: 600,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            padding: '6px 16px',
            height: '30px',
            borderRadius: '5px',
            border: `1px solid ${selectedOrgId ? 'var(--accent-amber)' : 'var(--border-subtle)'}`,
            cursor: selectedOrgId ? 'pointer' : 'not-allowed',
            background: selectedOrgId ? 'var(--accent-amber-glow)' : 'transparent',
            color: selectedOrgId ? 'var(--accent-amber)' : 'var(--text-muted)',
            opacity: selectedOrgId ? 1 : 0.5,
            transition: 'background 0.15s ease',
          }}
        >
          Start baseline
        </button>
      ) : (
        <button
          onClick={onStartSweep}
          disabled={!selectedOrgId || state === 'running' || state === 'queued'}
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: '11px',
            fontWeight: 600,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            padding: '6px 16px',
            height: '30px',
            borderRadius: '5px',
            border: '1px solid var(--border-subtle)',
            cursor: (!selectedOrgId || state === 'running' || state === 'queued') ? 'not-allowed' : 'pointer',
            background: 'var(--bg-tertiary)',
            color: 'var(--text-primary)',
            opacity: (state === 'running' || state === 'queued') ? 0.5 : 1,
            transition: 'background 0.15s ease',
          }}
        >
          Run full sweep
        </button>
      )}
    </div>
  );
};
