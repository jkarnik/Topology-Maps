import React from 'react';

const TYPE_STYLES = {
  RowAdded:     { color: '#27ae60', prefix: '+' },
  FieldAdded:   { color: '#27ae60', prefix: '+' },
  RowRemoved:   { color: '#e74c3c', prefix: '−' },
  FieldRemoved: { color: '#e74c3c', prefix: '−' },
  RowChanged:   { color: '#e67e22', prefix: '~' },
  FieldChanged: { color: '#e67e22', prefix: '~' },
  SecretChanged:{ color: '#9b59b6', prefix: '🔒' },
};

function Change({ change }) {
  const style = TYPE_STYLES[change.type] || { color: '#aaa', prefix: '?' };
  const label = change.key || (change.identity != null ? `[${change.identity}]` : '?');
  let detail = '';
  if (change.type === 'FieldChanged') detail = ` ${JSON.stringify(change.before)} → ${JSON.stringify(change.after)}`;
  else if (change.type === 'RowChanged') detail = ` (${change.field_changes?.length || 0} field changes)`;
  return (
    <div style={{ fontFamily: 'monospace', fontSize: '12px', color: style.color, padding: '2px 0' }}>
      <span style={{ marginRight: '6px' }}>{style.prefix}</span>
      <span>{change.type}:</span>
      <span style={{ marginLeft: '6px', fontWeight: 'bold' }}>{label}</span>
      <span style={{ opacity: 0.7 }}>{detail}</span>
    </div>
  );
}

export default function DiffViewer({ diffJson }) {
  if (!diffJson) return null;
  let changes = [];
  try { changes = JSON.parse(diffJson); } catch (_) {
    return <span style={{ color: '#e74c3c' }}>Invalid diff JSON</span>;
  }
  if (!changes.length) return <span style={{ opacity: 0.6 }}>No changes recorded.</span>;
  return (
    <div style={{ background: 'rgba(128,128,128,0.08)', border: '1px solid rgba(128,128,128,0.15)',
                  padding: '12px', borderRadius: '4px', maxHeight: '300px', overflow: 'auto' }}>
      {changes.map((c, i) => <Change key={i} change={c} />)}
    </div>
  );
}
