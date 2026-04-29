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

function HistoryTreeNode({ label, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <div onClick={() => setOpen(o => !o)} style={{ cursor: 'pointer', padding: '3px 0', fontWeight: 'bold', userSelect: 'none', fontSize: '12px', opacity: 0.7 }}>
        {open ? '▾' : '▸'} {label}
      </div>
      {open && <div style={{ paddingLeft: '12px' }}>{children}</div>}
    </div>
  );
}

function HistoryEntityItem({ entity, selected, onSelect }) {
  return (
    <div onClick={onSelect} style={{
      padding: '2px 4px', cursor: 'pointer', borderRadius: '3px', marginBottom: '1px', fontSize: '12px',
      color: selected ? '#0078bf' : 'inherit',
      background: selected ? 'rgba(0,120,191,0.12)' : 'transparent',
    }}>
      {selected ? '●' : '○'} {entity.entityName}
      <span style={{ opacity: 0.5, marginLeft: '4px' }}>({entity.count})</span>
    </div>
  );
}

function EntityTree({ accountId, orgId, fromDate, toDate, selectedId, onSelect }) {
  const fromISO = fromDate.toISOString().slice(0, 10);
  const toISO = toDate.toISOString().slice(0, 10);
  return (
    <div>
      <div style={{ fontSize: '11px', opacity: 0.6, marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Changed Entities</div>
      <NrqlQuery accountIds={[accountId]}
        query={`SELECT latest(entity_name) FROM MerakiConfigSnapshot WHERE entity_type = 'network' AND org_id = '${orgId}' FACET entity_id SINCE 30 days ago LIMIT MAX`}>
        {({ data: netData }) => {
          const netNames = {};
          (netData || []).forEach(s => {
            const fg = (s.metadata?.groups || []).filter(g => g.type === 'facet');
            const id = fg[0]?.value;
            const name = s.data?.[0]?.['entity_name'];
            if (id && name) netNames[id] = name;
          });
          return (
            <NrqlQuery accountIds={[accountId]}
              query={`SELECT count(*) FROM MerakiConfigChange WHERE org_id = '${orgId}' FACET entity_type, entity_id, entity_name, network_id SINCE '${fromISO}' UNTIL '${toISO}' LIMIT MAX`}>
              {({ data, loading, error }) => {
                if (loading) return <Spinner />;
                if (error) return <p style={{ color: '#c0392b', fontSize: '12px' }}>Failed to load.</p>;
                const entities = [];
                (data || []).forEach(s => {
                  const fg = (s.metadata?.groups || []).filter(g => g.type === 'facet');
                  const entityType = fg[0]?.value;
                  const entityId = fg[1]?.value;
                  const entityName = fg[2]?.value;
                  const networkId = fg[3]?.value;
                  const count = s.data?.[0]?.count || 0;
                  if (!entityId || !count) return;
                  entities.push({ entityType, entityId, entityName: entityName || entityId, networkId, count });
                });
                if (!entities.length) return <p style={{ opacity: 0.5, fontSize: '12px' }}>No changes in range.</p>;
                const networks = {};
                entities.forEach(e => {
                  const netId = e.entityType === 'network' ? e.entityId
                    : e.entityType === 'ssid' ? e.entityId.split(':')[0]
                    : e.networkId || '__unknown';
                  if (!networks[netId]) networks[netId] = { id: netId, name: netNames[netId] || netId, items: [] };
                  networks[netId].items.push(e);
                });
                return (
                  <div style={{ fontFamily: 'monospace' }}>
                    {Object.values(networks).map(net => (
                      <HistoryTreeNode key={net.id} label={net.name} defaultOpen>
                        {net.items.map(e => (
                          <HistoryEntityItem key={e.entityId} entity={e}
                            selected={selectedId === e.entityId}
                            onSelect={() => onSelect(e.entityId, e.entityName)} />
                        ))}
                      </HistoryTreeNode>
                    ))}
                  </div>
                );
              }}
            </NrqlQuery>
          );
        }}
      </NrqlQuery>
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
        <EntityTree accountId={accountId} orgId={orgId} fromDate={fromDate} toDate={toDate}
          selectedId={selectedEntityId} onSelect={handleSelect} />
      </div>
      <div style={{ flex: 1, paddingLeft: '16px', overflowY: 'auto' }}>
        <div style={{ opacity: 0.4, fontSize: '13px' }}>Diff tiles coming soon…</div>
      </div>
    </div>
  );
}
