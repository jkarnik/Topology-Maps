import React from 'react';
import type { ConfigOrg, ConfigStatus } from '../../types/config';

interface Props {
  orgs: ConfigOrg[];
  selectedOrgId: string | null;
  status: ConfigStatus | null;
  onOrgChange: (orgId: string) => void;
  onStartBaseline: () => void;
  onStartSweep: () => void;
  baselineTimestamps: string[];
  onCompare: (fromTs: string, toTs?: string) => void;
  comparing: boolean;
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

export const CollectionStatusBar: React.FC<Props> = ({
  orgs, selectedOrgId, status, onOrgChange, onStartBaseline, onStartSweep,
  baselineTimestamps, onCompare, comparing,
}) => {
  const state = status?.active_sweep?.status ?? status?.baseline_state ?? 'none';
  const chip = statusChip(state);

  // FIX: only true when we have a status AND it's not 'none'
  const hasBaselined = !!status && status.baseline_state !== 'none';

  const [fromTs, setFromTs] = React.useState<string>('');
  const [toTs, setToTs] = React.useState<string>('');

  React.useEffect(() => {
    if (!fromTs && baselineTimestamps.length > 0) {
      setFromTs(baselineTimestamps[0]);
    }
  }, [baselineTimestamps]);

  const selectStyle: React.CSSProperties = {
    background: 'var(--bg-tertiary)',
    color: 'var(--text-primary)',
    border: '1px solid var(--border-subtle)',
    borderRadius: '5px',
    padding: '4px 8px',
    fontSize: '11px',
    ...MONO,
    cursor: 'pointer',
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'stretch',
        padding: '10px 20px',
        background: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border-subtle)',
        ...MONO,
      }}
    >
      {/* Row 1: org selector, status chip, action button */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
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
          {status?.last_sync && (
            <span style={{ color: 'var(--text-muted)', fontWeight: 400, marginLeft: '4px' }}>
              {new Date(status.last_sync).toLocaleString()}
            </span>
          )}
        </span>

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* Action button */}
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

      {/* Row 2: Compare time range selectors */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          paddingTop: '8px',
          marginTop: '8px',
          borderTop: '1px solid var(--border-subtle)',
        }}
      >
        <span style={{ fontSize: '11px', color: 'var(--text-secondary)', letterSpacing: '0.06em' }}>
          Compare:
        </span>

        {/* From select */}
        <select
          value={fromTs}
          onChange={(e) => setFromTs(e.target.value)}
          style={selectStyle}
        >
          <option value="">— select from —</option>
          {baselineTimestamps.map((ts) => (
            <option key={ts} value={ts}>
              {new Date(ts).toLocaleString()}
            </option>
          ))}
          <option value="last7">Last 7 days</option>
          <option value="last30">Last 30 days</option>
        </select>

        <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>→</span>

        {/* To select */}
        <select
          value={toTs}
          onChange={(e) => setToTs(e.target.value)}
          style={selectStyle}
        >
          <option value="">Now (latest)</option>
          {baselineTimestamps.map((ts) => (
            <option key={ts} value={ts}>
              {new Date(ts).toLocaleString()}
            </option>
          ))}
        </select>

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* Compare button */}
        <button
          disabled={!fromTs || comparing}
          onClick={() => {
            const resolvedFrom =
              fromTs === 'last7'
                ? new Date(Date.now() - 7 * 86400_000).toISOString()
                : fromTs === 'last30'
                ? new Date(Date.now() - 30 * 86400_000).toISOString()
                : fromTs;
            onCompare(resolvedFrom, toTs || undefined);
          }}
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
            cursor: (!fromTs || comparing) ? 'not-allowed' : 'pointer',
            background: 'var(--bg-tertiary)',
            color: (!fromTs || comparing) ? 'var(--text-muted)' : 'var(--text-primary)',
            opacity: (!fromTs || comparing) ? 0.5 : 1,
            transition: 'background 0.15s ease',
          }}
        >
          {comparing ? 'Loading…' : 'Compare'}
        </button>
      </div>
    </div>
  );
};
