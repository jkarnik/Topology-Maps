import React, { useState } from 'react';
import { DataSource, ViewMode } from '../types/topology';
import { MerakiNetwork } from '../types/meraki';
import { SourceSelector } from './SourceSelector';
import { NetworkFilter } from './NetworkFilter';

interface TopBarProps {
  dataSource: DataSource;
  onDataSourceChange: (source: DataSource) => void;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  isConnected: boolean;
  pollCount: number;
  simulationRunning: boolean;
  simulationRemaining: number;
  onSimulationStart: () => void;
  onSimulationStop: () => void;
  merakiNetworks: MerakiNetwork[];
  selectedNetwork: string | null;
  onNetworkChange: (id: string | null) => void;
  isRefreshing: boolean;
  lastUpdated: Date | null;
  onRefresh: () => void;
  onSaveSnapshot: () => Promise<boolean>;
}

/** Convert seconds to "M:SS" format */
function formatTime(seconds: number): string {
  const total = Math.floor(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

/** Convert a past Date to "Xm ago" or "just now" */
function formatAgo(date: Date): string {
  const diffMs = Date.now() - date.getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return 'just now';
  return `${diffMin}m ago`;
}

const VIEW_MODES: { id: ViewMode; label: string }[] = [
  { id: 'l2', label: 'L2' },
  { id: 'hybrid', label: 'L2+L3' },
  { id: 'l3', label: 'L3' },
];

export const TopBar: React.FC<TopBarProps> = ({
  dataSource,
  onDataSourceChange,
  viewMode,
  onViewModeChange,
  // isConnected is kept in the props interface for future use (e.g. connection badge)
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  isConnected: _isConnected,
  pollCount,
  simulationRunning,
  simulationRemaining,
  onSimulationStart,
  onSimulationStop,
  merakiNetworks,
  selectedNetwork,
  onNetworkChange,
  isRefreshing,
  lastUpdated,
  onRefresh,
  onSaveSnapshot,
}) => {
  const accentColor = dataSource === 'simulated' ? 'var(--accent-cyan)' : 'var(--accent-amber)';

  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const handleSaveSnapshot = async () => {
    if (saveStatus === 'saving') return;
    setSaveStatus('saving');
    const ok = await onSaveSnapshot();
    setSaveStatus(ok ? 'saved' : 'error');
    setTimeout(() => setSaveStatus('idle'), 2000);
  };

  return (
    <header
      style={{
        height: '56px',
        background: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border-subtle)',
        display: 'flex',
        alignItems: 'center',
        padding: '0 20px',
        gap: '12px',
        flexShrink: 0,
        position: 'relative',
        zIndex: 50,
        fontFamily: "'JetBrains Mono', monospace",
      }}
    >
      {/* Left: Source selector */}
      <SourceSelector value={dataSource} onChange={onDataSourceChange} />

      {/* Network filter — Meraki only */}
      {dataSource === 'meraki' && (
        <NetworkFilter
          networks={merakiNetworks}
          value={selectedNetwork}
          onChange={onNetworkChange}
        />
      )}

      {/* Center: View mode pills — not applicable to Configs workspace */}
      {dataSource !== 'configs' && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            background: 'var(--bg-primary)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '999px',
            padding: '3px',
            gap: '2px',
            marginLeft: dataSource === 'meraki' ? '0' : '4px',
          }}
        >
          {VIEW_MODES.map(({ id, label }) => {
            const isActive = viewMode === id;
            return (
              <button
                key={id}
                onClick={() => onViewModeChange(id)}
                style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: '12px',
                  fontWeight: 600,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  padding: '5px 18px',
                  borderRadius: '999px',
                  border: 'none',
                  cursor: 'pointer',
                  transition: 'background 0.15s ease, color 0.15s ease',
                  background: isActive ? accentColor : 'transparent',
                  color: isActive ? 'var(--bg-primary)' : 'var(--text-secondary)',
                  lineHeight: 1,
                }}
              >
                {label}
              </button>
            );
          })}
        </div>
      )}

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Right controls */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        {dataSource === 'simulated' ? (
          simulationRunning ? (
            <>
              {/* Live indicator */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '7px',
                  fontSize: '11px',
                  letterSpacing: '0.1em',
                }}
              >
                <span
                  className="animate-pulse-dot"
                  style={{
                    display: 'inline-block',
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    background: 'var(--accent-green)',
                    boxShadow: '0 0 6px rgba(0, 214, 143, 0.6)',
                    flexShrink: 0,
                  }}
                />
                <span style={{ color: 'var(--accent-green)', fontWeight: 600 }}>LIVE</span>
                <span style={{ color: 'var(--text-muted)' }}>#{pollCount}</span>
              </div>

              {/* Countdown */}
              <div
                style={{
                  fontSize: '11px',
                  color: 'var(--accent-amber)',
                  fontWeight: 500,
                  letterSpacing: '0.06em',
                }}
              >
                {formatTime(simulationRemaining)} remaining
              </div>

              {/* Stop button */}
              <button
                onClick={onSimulationStop}
                style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: '11px',
                  fontWeight: 600,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  padding: '5px 14px',
                  height: '30px',
                  borderRadius: '5px',
                  border: '1px solid var(--accent-red)',
                  cursor: 'pointer',
                  background: 'rgba(255, 71, 87, 0.12)',
                  color: 'var(--accent-red)',
                  transition: 'background 0.15s ease',
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255, 71, 87, 0.22)';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.background = 'rgba(255, 71, 87, 0.12)';
                }}
              >
                Stop
              </button>
            </>
          ) : (
            /* Start simulation button */
            <button
              onClick={onSimulationStart}
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '11px',
                fontWeight: 600,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                padding: '5px 16px',
                height: '30px',
                borderRadius: '5px',
                border: '1px solid var(--accent-cyan)',
                cursor: 'pointer',
                background: 'rgba(0, 229, 200, 0.12)',
                color: 'var(--accent-cyan)',
                transition: 'background 0.15s ease',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = 'rgba(0, 229, 200, 0.22)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = 'rgba(0, 229, 200, 0.12)';
              }}
            >
              Start Simulation
            </button>
          )
        ) : (
          /* Meraki right controls */
          <>
            {/* Last updated timestamp */}
            <span
              style={{
                fontSize: '11px',
                color: 'var(--text-muted)',
                letterSpacing: '0.06em',
              }}
            >
              Updated{' '}
              <span style={{ color: 'var(--text-secondary)' }}>
                {lastUpdated ? formatAgo(lastUpdated) : '—'}
              </span>
            </span>

            {/* Refresh button */}
            <button
              onClick={() => onRefresh()}
              disabled={isRefreshing}
              title="Refresh topology"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '30px',
                height: '30px',
                borderRadius: '5px',
                border: '1px solid var(--border-subtle)',
                cursor: isRefreshing ? 'not-allowed' : 'pointer',
                background: 'var(--bg-tertiary)',
                color: isRefreshing ? 'var(--text-muted)' : 'var(--accent-amber)',
                opacity: isRefreshing ? 0.6 : 1,
                transition: 'opacity 0.15s ease, color 0.15s ease',
              }}
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 14 14"
                fill="none"
                className={isRefreshing ? 'spin' : undefined}
                style={{ color: 'inherit' }}
              >
                <path
                  d="M12.5 2.5A6 6 0 1 1 7 1"
                  stroke="currentColor"
                  strokeWidth="1.4"
                  strokeLinecap="round"
                />
                <path
                  d="M7 1l2.5 2.5L7 6"
                  stroke="currentColor"
                  strokeWidth="1.4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>

            {/* Save snapshot button — writes the current cache into
                ui/public/meraki-topology-seed.json so the next fresh
                clone can render without any Meraki API calls. */}
            <button
              onClick={handleSaveSnapshot}
              disabled={saveStatus === 'saving'}
              title={
                saveStatus === 'saved'
                  ? 'Saved to ui/public/meraki-topology-seed.json'
                  : saveStatus === 'error'
                  ? 'Save failed — check backend logs'
                  : 'Save current cache to seed file'
              }
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '5px',
                height: '30px',
                padding: saveStatus === 'saved' || saveStatus === 'error' ? '0 10px' : '0',
                width: saveStatus === 'saved' || saveStatus === 'error' ? 'auto' : '30px',
                borderRadius: '5px',
                border: '1px solid var(--border-subtle)',
                cursor: saveStatus === 'saving' ? 'not-allowed' : 'pointer',
                background: 'var(--bg-tertiary)',
                color:
                  saveStatus === 'saved'
                    ? 'var(--accent-green)'
                    : saveStatus === 'error'
                    ? 'var(--accent-red)'
                    : 'var(--accent-amber)',
                opacity: saveStatus === 'saving' ? 0.6 : 1,
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '11px',
                fontWeight: 600,
                letterSpacing: '0.04em',
                transition: 'color 0.15s ease',
              }}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                {/* Floppy-disk shape */}
                <path
                  d="M2 2h7.5L12 4.5V12H2V2z"
                  stroke="currentColor"
                  strokeWidth="1.3"
                  strokeLinejoin="round"
                />
                <path
                  d="M4 2v3h5V2M4 12v-4h5v4"
                  stroke="currentColor"
                  strokeWidth="1.3"
                  strokeLinejoin="round"
                />
              </svg>
              {saveStatus === 'saved' && <span>SAVED</span>}
              {saveStatus === 'error' && <span>ERR</span>}
            </button>
          </>
        )}
      </div>
    </header>
  );
};

export default TopBar;
