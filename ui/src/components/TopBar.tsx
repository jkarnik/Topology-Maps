import React from 'react';

interface TopBarProps {
  viewMode: 'l2' | 'l3' | 'hybrid';
  onViewModeChange: (mode: 'l2' | 'l3' | 'hybrid') => void;
  isConnected: boolean;
  pollCount: number;
}

export const TopBar: React.FC<TopBarProps> = ({
  viewMode,
  onViewModeChange,
  isConnected,
  pollCount,
}) => {
  return (
    <header
      style={{
        height: '56px',
        background: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border-subtle)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 20px',
        flexShrink: 0,
        position: 'relative',
        zIndex: 50,
      }}
    >
      {/* Left: App Title */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
        <span
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: '15px',
            fontWeight: 700,
            letterSpacing: '0.22em',
            textTransform: 'uppercase',
            color: 'var(--text-primary)',
            lineHeight: 1,
          }}
        >
          TOPOLOGY
        </span>
        <div
          style={{
            height: '2px',
            width: '100%',
            background: 'var(--accent-cyan)',
            borderRadius: '1px',
          }}
        />
      </div>

      {/* Center: L2 / L3 Toggle */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          background: 'var(--bg-primary)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '999px',
          padding: '3px',
          gap: '2px',
        }}
      >
        {([['l2', 'L2'], ['hybrid', 'L2+L3'], ['l3', 'L3']] as const).map(([mode, label]) => {
          const isActive = viewMode === mode;
          return (
            <button
              key={mode}
              onClick={() => onViewModeChange(mode)}
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
                background: isActive ? 'var(--accent-cyan)' : 'transparent',
                color: isActive ? 'var(--bg-primary)' : 'var(--text-secondary)',
                lineHeight: 1,
              }}
            >
              {label}
            </button>
          );
        })}
      </div>

      {/* Right: Live Indicator */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        {/* Live Polling Indicator */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '7px',
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: '11px',
            letterSpacing: '0.1em',
          }}
        >
          <span
            className={isConnected ? 'animate-pulse-dot' : undefined}
            style={{
              display: 'inline-block',
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              background: isConnected ? 'var(--accent-green)' : 'var(--accent-red)',
              boxShadow: isConnected
                ? '0 0 6px rgba(0, 214, 143, 0.6)'
                : '0 0 6px rgba(255, 71, 87, 0.5)',
              flexShrink: 0,
            }}
          />
          {isConnected ? (
            <span style={{ color: 'var(--text-secondary)' }}>
              <span style={{ color: 'var(--accent-green)', fontWeight: 600 }}>LIVE</span>
              {' '}
              <span style={{ color: 'var(--text-muted)' }}>#{pollCount}</span>
            </span>
          ) : (
            <span style={{ color: 'var(--accent-red)', fontWeight: 600 }}>OFFLINE</span>
          )}
        </div>
      </div>
    </header>
  );
};

export default TopBar;
