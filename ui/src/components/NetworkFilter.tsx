import React, { useState, useRef, useEffect } from 'react';
import { MerakiNetwork } from '../types/meraki';

interface NetworkFilterProps {
  networks: MerakiNetwork[];
  value: string | null;
  onChange: (id: string | null) => void;
}

export const NetworkFilter: React.FC<NetworkFilterProps> = ({ networks, value, onChange }) => {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  const selectedNetwork = networks.find((n) => n.id === value) ?? null;
  const displayLabel = selectedNetwork ? selectedNetwork.name : 'All Networks';

  return (
    <div ref={containerRef} style={{ position: 'relative' }}>
      {/* Trigger button */}
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          height: '32px',
          padding: '0 12px',
          background: 'var(--bg-tertiary)',
          border: `1px solid ${open ? 'var(--accent-amber)' : 'var(--border-subtle)'}`,
          borderRadius: '6px',
          cursor: 'pointer',
          transition: 'border-color 0.15s ease',
          fontFamily: "'JetBrains Mono', monospace",
        }}
      >
        {/* Network icon */}
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          style={{ color: 'var(--accent-amber)', flexShrink: 0 }}
        >
          <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.3" />
          <path d="M6 1C6 1 4 3.5 4 6s2 5 2 5" stroke="currentColor" strokeWidth="1.3" />
          <path d="M6 1C6 1 8 3.5 8 6s-2 5-2 5" stroke="currentColor" strokeWidth="1.3" />
          <path d="M1 6h10" stroke="currentColor" strokeWidth="1.3" />
        </svg>
        {/* Label */}
        <span
          style={{
            fontSize: '12px',
            fontWeight: 600,
            color: 'var(--text-primary)',
            letterSpacing: '0.04em',
            maxWidth: '140px',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {displayLabel}
        </span>
        {/* Chevron */}
        <svg
          width="10"
          height="6"
          viewBox="0 0 10 6"
          fill="none"
          style={{
            color: 'var(--text-muted)',
            transition: 'transform 0.15s ease',
            transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
          }}
        >
          <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {/* Dropdown */}
      {open && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            left: 0,
            minWidth: '200px',
            maxHeight: '280px',
            overflowY: 'auto',
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '8px',
            zIndex: 200,
            boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
          }}
        >
          {/* All Networks option */}
          {[{ id: null, name: 'All Networks' }, ...networks].map((net) => {
            const isSelected = net.id === value;
            return (
              <button
                key={net.id ?? '__all__'}
                onClick={() => {
                  onChange(net.id);
                  setOpen(false);
                }}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  padding: '9px 14px',
                  background: isSelected ? 'var(--bg-tertiary)' : 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                  fontFamily: "'JetBrains Mono', monospace",
                  textAlign: 'left',
                  transition: 'background 0.1s ease',
                }}
                onMouseEnter={(e) => {
                  if (!isSelected) (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-surface)';
                }}
                onMouseLeave={(e) => {
                  if (!isSelected) (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                }}
              >
                {/* Selection indicator */}
                <span
                  style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    background: isSelected ? 'var(--accent-amber)' : 'transparent',
                    border: isSelected ? 'none' : '1px solid var(--border-subtle)',
                    flexShrink: 0,
                  }}
                />
                <span
                  style={{
                    fontSize: '12px',
                    fontWeight: isSelected ? 600 : 400,
                    color: isSelected ? 'var(--text-primary)' : 'var(--text-secondary)',
                    letterSpacing: '0.03em',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {net.name}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default NetworkFilter;
