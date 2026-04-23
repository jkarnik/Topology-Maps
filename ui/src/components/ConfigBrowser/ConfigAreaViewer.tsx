import React, { useState } from 'react';
import JsonView from '@uiw/react-json-view';
import type { ConfigArea } from '../../types/config';

interface Props {
  area: ConfigArea;
  onRefresh: () => void;
  refreshing: boolean;
}

const MONO: React.CSSProperties = { fontFamily: "'JetBrains Mono', monospace" };

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const sec = Math.round(diff / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const d = Math.round(hr / 24);
  return `${d}d ago`;
}

function sourceEventColor(e: string): string {
  switch (e) {
    case 'baseline': return 'var(--accent-cyan)';
    case 'change_log': return 'var(--accent-amber)';
    case 'anti_drift_confirm': return 'var(--accent-green)';
    case 'anti_drift_discrepancy': return 'var(--accent-red)';
    case 'manual_refresh': return 'var(--text-primary)';
    default: return 'var(--text-muted)';
  }
}

// Override @uiw/react-json-view colors to fit our palette
const JSON_VIEWER_STYLE: React.CSSProperties = {
  background: 'transparent',
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: '11.5px',
  '--w-rjv-color': 'var(--text-primary)',
  '--w-rjv-key-string': 'var(--accent-amber)',
  '--w-rjv-key-number': 'var(--accent-cyan)',
  '--w-rjv-type-string-color': 'var(--accent-green)',
  '--w-rjv-type-int-color': 'var(--accent-cyan)',
  '--w-rjv-type-float-color': 'var(--accent-cyan)',
  '--w-rjv-type-bigint-color': 'var(--accent-cyan)',
  '--w-rjv-type-boolean-color': 'var(--accent-purple, #b07aff)',
  '--w-rjv-type-null-color': 'var(--text-muted)',
  '--w-rjv-type-undefined-color': 'var(--text-muted)',
  '--w-rjv-type-nan-color': 'var(--accent-red)',
  '--w-rjv-colon-color': 'var(--text-muted)',
  '--w-rjv-arrow-color': 'var(--text-secondary)',
  '--w-rjv-curlybraces-color': 'var(--text-secondary)',
  '--w-rjv-brackets-color': 'var(--text-secondary)',
  '--w-rjv-info-color': 'var(--text-muted)',
  '--w-rjv-update-color': 'var(--accent-amber)',
  '--w-rjv-background-color': 'transparent',
  '--w-rjv-line-color': 'var(--border-subtle)',
} as React.CSSProperties;

export const ConfigAreaViewer: React.FC<Props> = ({ area, onRefresh, refreshing }) => {
  const [open, setOpen] = useState(false);
  const label = area.config_area.replace(/_/g, ' ');

  return (
    <div
      style={{
        border: '1px solid var(--border-subtle)',
        borderRadius: '6px',
        marginBottom: '8px',
        background: 'var(--bg-surface)',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '8px 12px',
          background: 'var(--bg-secondary)',
          borderBottom: open ? '1px solid var(--border-subtle)' : 'none',
          ...MONO,
        }}
      >
        <button
          onClick={() => setOpen((o) => !o)}
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--text-primary)',
            cursor: 'pointer',
            fontSize: '12px',
            padding: 0,
            fontFamily: "'JetBrains Mono', monospace",
            fontWeight: 500,
          }}
        >
          <span style={{ color: 'var(--text-muted)', marginRight: '6px' }}>
            {open ? '▾' : '▸'}
          </span>
          {label}
        </button>
        <span
          style={{
            marginLeft: 'auto',
            fontSize: '10px',
            color: 'var(--text-muted)',
            letterSpacing: '0.06em',
          }}
        >
          last: {relativeTime(area.observed_at)}
          <span style={{ color: sourceEventColor(area.source_event), marginLeft: '6px' }}>
            ({area.source_event})
          </span>
        </span>
        <button
          onClick={onRefresh}
          disabled={refreshing}
          title="Refresh this area"
          style={{
            background: 'var(--bg-tertiary)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '4px',
            color: refreshing ? 'var(--text-muted)' : 'var(--accent-amber)',
            cursor: refreshing ? 'not-allowed' : 'pointer',
            width: '24px',
            height: '24px',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '13px',
            opacity: refreshing ? 0.6 : 1,
          }}
        >
          <span className={refreshing ? 'spin' : undefined}>↻</span>
        </button>
      </div>
      {open && (
        <div
          style={{
            padding: '10px 12px',
            background: 'var(--bg-primary)',
            maxHeight: '420px',
            overflow: 'auto',
          }}
        >
          <JsonView
            value={area.payload as object}
            displayDataTypes={false}
            collapsed={2}
            style={JSON_VIEWER_STYLE}
          />
        </div>
      )}
    </div>
  );
};
