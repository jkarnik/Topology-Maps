import React, { useState } from 'react';
import { NrqlQuery, Spinner } from 'nr1';

function highlightJson(raw) {
  let pretty = raw;
  try { pretty = JSON.stringify(JSON.parse(raw), null, 2); } catch (_) {}
  return pretty
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(
      /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g,
      match => {
        if (/^"/.test(match)) {
          return /:$/.test(match)
            ? `<span class="json-key">${match}</span>`
            : `<span class="json-str">${match}</span>`;
        }
        if (/true|false/.test(match)) return `<span class="json-bool">${match}</span>`;
        if (/null/.test(match))       return `<span class="json-null">${match}</span>`;
        return `<span class="json-num">${match}</span>`;
      }
    );
}

export default function ConfigAreaViewer({ accountId, entityId, entityType }) {
  const [openAreas, setOpenAreas] = useState(new Set());

  function toggleArea(area) {
    setOpenAreas(prev => {
      const next = new Set(prev);
      next.has(area) ? next.delete(area) : next.add(area);
      return next;
    });
  }

  if (!entityId) return <p style={{ opacity: 0.6 }}>Select an entity to view its config.</p>;
  if (!accountId) return <p style={{ opacity: 0.6 }}>No account.</p>;

  return (
    <div>
      <style>{`
        .json-key  { color: #0066cc; }
        .json-str  { color: #a31515; }
        .json-num  { color: #098658; }
        .json-bool { color: #0000ff; }
        .json-null { color: #dd0000; }
        @media (prefers-color-scheme: dark) {
          .json-key  { color: #9cdcfe; }
          .json-str  { color: #ce9178; }
          .json-num  { color: #b5cea8; }
          .json-bool { color: #569cd6; }
          .json-null { color: #f44747; }
        }
      `}</style>
      <h3 style={{ marginBottom: '12px', fontSize: '14px' }}>
        {entityType}: {entityId}
      </h3>
      <NrqlQuery
        accountIds={[accountId]}
        query={`SELECT latest(config_hash), latest(observed_at) FROM MerakiConfigSnapshot
                WHERE entity_id = '${entityId}'
                FACET config_area SINCE 30 days ago LIMIT MAX`}
      >
        {({ data, loading, error }) => {
          if (loading) return <Spinner />;
          if (error) return <p style={{ color: '#c0392b' }}>Query failed: {String(error.message || error)}</p>;
          if (!data || !data.length) return <p style={{ opacity: 0.6 }}>No config data found.</p>;

          const seen = new Set();
          const areas = (data || []).reduce((acc, s) => {
            const area = (s.metadata?.groups || []).find(g => g.type === 'facet')?.value;
            if (!area || seen.has(area)) return acc;
            seen.add(area);
            const hash = s.data?.[0]?.['config_hash'] || s.data?.[0]?.['latest.config_hash'] || '';
            const ts   = s.data?.[0]?.['observed_at'] || s.data?.[0]?.['latest.observed_at'] || '';
            acc.push({ area, hash, ts });
            return acc;
          }, []);

          if (!areas.length) return <p style={{ opacity: 0.6 }}>No config areas found.</p>;

          return (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {areas.map(({ area, hash, ts }) => {
                const isOpen = openAreas.has(area);
                return (
                  <div
                    key={area}
                    style={{ border: '1px solid rgba(128,128,128,0.2)', borderRadius: '6px', overflow: 'hidden' }}
                  >
                    <div
                      onClick={() => toggleArea(area)}
                      style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                        padding: '10px 14px', cursor: 'pointer', userSelect: 'none',
                        fontFamily: 'monospace', fontSize: '13px',
                        background: isOpen ? 'rgba(0,120,191,0.12)' : 'rgba(128,128,128,0.05)',
                        color: isOpen ? '#0078bf' : 'inherit',
                        borderBottom: isOpen ? '1px solid rgba(128,128,128,0.15)' : undefined,
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <span style={{
                          fontSize: '12px', opacity: isOpen ? 1 : 0.4,
                          color: isOpen ? '#0078bf' : 'inherit',
                          display: 'inline-block',
                          transform: isOpen ? 'rotate(90deg)' : undefined,
                          transition: 'transform 0.15s',
                        }}>▶</span>
                        <span style={{ fontWeight: 'bold' }}>{area}</span>
                        <span style={{ opacity: 0.5, fontSize: '11px' }}>{hash.slice(0, 8)} · {ts ? new Date(ts).toLocaleString() : ''}</span>
                      </div>
                    </div>
                    {isOpen && (
                      <div style={{ padding: '12px 14px', background: 'rgba(128,128,128,0.04)' }}>
                        <ConfigJson accountId={accountId} entityId={entityId} configArea={area} />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          );
        }}
      </NrqlQuery>
    </div>
  );
}

function ConfigJson({ accountId, entityId, configArea }) {
  return (
    <NrqlQuery
      accountIds={[accountId]}
      query={`SELECT latest(config_json) FROM MerakiConfigSnapshot
              WHERE entity_id = '${entityId}' AND config_area = '${configArea}'
              SINCE 30 days ago`}
    >
      {({ data, loading, error }) => {
        if (loading) return <Spinner />;
        if (error) return <p style={{ color: '#c0392b', fontSize: '12px', margin: 0 }}>Query failed: {String(error.message || error)}</p>;
        const raw = data?.[0]?.data?.[0]?.['config_json'] || data?.[0]?.data?.[0]?.['latest.config_json'] || '{}';
        return (
          <pre
            style={{
              background: 'rgba(128,128,128,0.08)', padding: '12px',
              borderRadius: '4px', overflow: 'auto', maxHeight: '400px',
              margin: '0', fontSize: '12px', border: '1px solid rgba(128,128,128,0.15)',
              fontFamily: 'monospace', lineHeight: '1.6',
            }}
            dangerouslySetInnerHTML={{ __html: highlightJson(raw) }}
          />
        );
      }}
    </NrqlQuery>
  );
}
