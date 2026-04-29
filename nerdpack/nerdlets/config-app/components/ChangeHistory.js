import React, { useState } from 'react';
import { NrqlQuery, Spinner } from 'nr1';

function daysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  d.setHours(0, 0, 0, 0);
  return d;
}

function DateRangePanel({ fromDate, toDate, onRangeChange, activeShortcut, onShortcut }) {
  function setShortcut(days) {
    const to = new Date();
    to.setHours(23, 59, 59, 999);
    const from = daysAgo(days);
    onRangeChange(from, to);
    onShortcut(days);
  }
  function toInputVal(d) { return d.toISOString().slice(0, 10); }
  return (
    <div style={{ marginBottom: '16px' }}>
      <div style={{ fontSize: '11px', opacity: 0.6, marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Date Range</div>
      <div style={{ marginBottom: '6px', fontSize: '12px' }}>
        <label style={{ display: 'block', opacity: 0.6, marginBottom: '2px' }}>From</label>
        <input type="date" value={toInputVal(fromDate)} max={toInputVal(toDate)}
          onChange={e => { onRangeChange(new Date(e.target.value + 'T00:00:00'), toDate); onShortcut(null); }}
          style={{ width: '100%', fontSize: '12px', padding: '2px 4px', background: 'transparent', border: '1px solid rgba(128,128,128,0.3)', borderRadius: '3px', color: 'inherit' }} />
      </div>
      <div style={{ marginBottom: '8px', fontSize: '12px' }}>
        <label style={{ display: 'block', opacity: 0.6, marginBottom: '2px' }}>To</label>
        <input type="date" value={toInputVal(toDate)} min={toInputVal(fromDate)}
          onChange={e => { onRangeChange(fromDate, new Date(e.target.value + 'T23:59:59')); onShortcut(null); }}
          style={{ width: '100%', fontSize: '12px', padding: '2px 4px', background: 'transparent', border: '1px solid rgba(128,128,128,0.3)', borderRadius: '3px', color: 'inherit' }} />
      </div>
      <div style={{ display: 'flex', gap: '4px' }}>
        {[7, 30, 90].map(d => (
          <button key={d} onClick={() => setShortcut(d)} style={{
            flex: 1, fontSize: '11px', padding: '3px 0', cursor: 'pointer',
            background: activeShortcut === d ? 'rgba(0,120,191,0.15)' : 'transparent',
            border: `1px solid ${activeShortcut === d ? '#0078bf' : 'rgba(128,128,128,0.3)'}`,
            borderRadius: '3px', color: activeShortcut === d ? '#0078bf' : 'inherit',
          }}>{d}d</button>
        ))}
      </div>
    </div>
  );
}

export default function ChangeHistory({ accountId, orgId }) {
  const [fromDate, setFromDate] = useState(daysAgo(30));
  const [toDate, setToDate] = useState(() => { const d = new Date(); d.setHours(23,59,59,999); return d; });
  const [shortcut, setShortcut] = useState(30);
  const [selectedEntityId, setSelectedEntityId] = useState(null);
  const [selectedEntityName, setSelectedEntityName] = useState(null);

  if (!accountId || !orgId) return <p style={{ opacity: 0.6 }}>Select an org to view change history.</p>;

  function handleSelect(entityId, entityName) {
    if (selectedEntityId === entityId) { setSelectedEntityId(null); setSelectedEntityName(null); }
    else { setSelectedEntityId(entityId); setSelectedEntityName(entityName); }
  }

  return (
    <div style={{ display: 'flex', height: '100%', gap: 0 }}>
      <div style={{ width: '220px', minWidth: '220px', borderRight: '1px solid rgba(128,128,128,0.2)', paddingRight: '12px', overflowY: 'auto' }}>
        <DateRangePanel fromDate={fromDate} toDate={toDate}
          onRangeChange={(f, t) => { setFromDate(f); setToDate(t); }}
          activeShortcut={shortcut} onShortcut={setShortcut} />
        <div style={{ fontSize: '11px', opacity: 0.4 }}>Entity tree coming soon…</div>
      </div>
      <div style={{ flex: 1, paddingLeft: '16px', overflowY: 'auto' }}>
        <div style={{ opacity: 0.4, fontSize: '13px' }}>Diff tiles coming soon…</div>
      </div>
    </div>
  );
}
