# Compare Tab Sub-tabs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Networks / Coverage / Templates pill-sub-tabs inside the existing Compare tab in `CompareView.js`.

**Architecture:** All changes are self-contained in one file — `nerdpack/nerdlets/config-app/components/CompareView.js`. The existing `NetworkSelector` and `SideBySideDiff` components stay unchanged; a pill-button `useState` toggle switches between three sub-views rendered in the same component tree. Coverage and Templates each add one new component above the default export. No backend changes.

**Tech Stack:** React (hooks), New Relic One SDK (`NrqlQuery`, `Spinner`, `Select`, `SelectItem`), CSS-in-JS (inline styles only — no new npm packages)

---

### Task 1: Pill navigation shell

**Files:**
- Modify: `nerdpack/nerdlets/config-app/components/CompareView.js`

Restructure `CompareView` to own a `subTab` state (`'networks' | 'coverage' | 'templates'`) and render pill buttons at the top. Existing `SideBySideDiff` and `NetworkSelector` logic stays exactly as-is — just wrapped under `subTab === 'networks'`. Coverage and Templates render placeholder `<p>` tags for now.

- [ ] **Step 1: Add `subTab` state and pill buttons to `CompareView`**

  Replace the `export default function CompareView` block (lines 24–41) with:

  ```jsx
  export default function CompareView({ accountId, orgId }) {
    const [netA, setNetA] = useState(null);
    const [netB, setNetB] = useState(null);
    const [subTab, setSubTab] = useState('networks');

    if (!orgId) return <p style={{ opacity: 0.6 }}>Select an org to compare networks.</p>;

    const pillStyle = (key) => ({
      padding: '5px 14px',
      borderRadius: '20px',
      border: subTab === key ? '1px solid #0078bf' : '1px solid rgba(128,128,128,0.3)',
      background: subTab === key ? 'rgba(0,120,191,0.15)' : 'transparent',
      color: subTab === key ? '#0078bf' : 'inherit',
      cursor: 'pointer',
      fontSize: '12px',
    });

    return (
      <div>
        <div style={{ display: 'flex', gap: '6px', marginBottom: '16px' }}>
          <button style={pillStyle('networks')} onClick={() => setSubTab('networks')}>Networks</button>
          <button style={pillStyle('coverage')} onClick={() => setSubTab('coverage')}>Coverage</button>
          <button style={pillStyle('templates')} onClick={() => setSubTab('templates')}>Templates</button>
        </div>

        {subTab === 'networks' && (
          <div>
            <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-end', marginBottom: '16px' }}>
              <NetworkSelector accountId={accountId} orgId={orgId} label="Network A" value={netA} onChange={setNetA} />
              <NetworkSelector accountId={accountId} orgId={orgId} label="Network B" value={netB} onChange={setNetB} />
            </div>
            {netA && netB && netA !== netB
              ? <SideBySideDiff accountId={accountId} netA={netA} netB={netB} />
              : <p style={{ opacity: 0.6 }}>Select two different networks to compare.</p>
            }
          </div>
        )}

        {subTab === 'coverage' && (
          <p style={{ opacity: 0.6 }}>Coverage coming soon…</p>
        )}

        {subTab === 'templates' && (
          <p style={{ opacity: 0.6 }}>Templates coming soon…</p>
        )}
      </div>
    );
  }
  ```

- [ ] **Step 2: Verify in browser**

  Run `cd nerdpack && npm start` (or `nr1 nerdpack:serve` if already running). Open the Config nerdpack. Go to Compare tab. Three pill buttons should appear — Networks, Coverage, Templates. Networks tab shows the existing diff UI. Coverage and Templates show placeholder text. Clicking pills switches the view.

- [ ] **Step 3: Commit**

  ```bash
  git add nerdpack/nerdlets/config-app/components/CompareView.js
  git commit -m "feat(nerdpack): add pill sub-tab shell to Compare tab (Networks/Coverage/Templates)"
  ```

---

### Task 2: Coverage tab

**Files:**
- Modify: `nerdpack/nerdlets/config-app/components/CompareView.js`

Add a `CoverageTab` component above the `CompareView` default export. Replace the Coverage placeholder with `<CoverageTab>`.

The NRQL query returns one series per (entity_id, config_area) pair. Each series has:
- `s.metadata.groups` — array of `{ type, value }` objects; filter to `type === 'facet'` → `fg[0].value` = entity_id, `fg[1].value` = config_area
- `s.data[0]` — object with a timestamp value keyed as `'latest.timestamp'` or `'timestamp'`

- [ ] **Step 1: Add `CoverageTab` before `CompareView`**

  Insert the following after the closing `}` of `SideBySideDiff` and before `export default function CompareView`:

  ```jsx
  function CoverageTab({ accountId, orgId }) {
    const query = `SELECT latest(timestamp) FROM MerakiConfigSnapshot
                   WHERE org_id = '${orgId}'
                   FACET entity_id, config_area
                   SINCE 30 days ago LIMIT MAX`;
    return (
      <NrqlQuery accountIds={[accountId]} query={query}>
        {({ data, loading, error }) => {
          if (loading) return <Spinner />;
          if (error) return <p style={{ color: '#c0392b' }}>Failed to load coverage data.</p>;

          const now = Date.now();
          const STALE_MS = 7 * 24 * 60 * 60 * 1000;

          const matrix = {};
          const allAreas = new Set();
          (data || []).forEach(s => {
            const fg = (s.metadata?.groups || []).filter(g => g.type === 'facet');
            const entityId = fg[0]?.value;
            const area = fg[1]?.value;
            if (!entityId || !area) return;
            const ts = s.data?.[0]?.['latest.timestamp'] ?? s.data?.[0]?.['timestamp'] ?? null;
            if (!matrix[entityId]) matrix[entityId] = {};
            matrix[entityId][area] = ts ? Number(ts) : null;
            allAreas.add(area);
          });

          const areas = [...allAreas].sort();
          const rows = Object.entries(matrix).map(([entityId, areaMap]) => {
            const observed = areas.filter(a => areaMap[a] != null).length;
            const pct = areas.length ? Math.round((observed / areas.length) * 100) : 0;
            return { entityId, areaMap, observed, pct };
          }).sort((a, b) => b.pct - a.pct);

          if (!rows.length) return <p style={{ opacity: 0.6 }}>No snapshot data found for this org.</p>;

          function cellColor(ts) {
            if (ts == null) return 'rgba(128,128,128,0.12)';
            return (now - ts) > STALE_MS ? '#e67e22' : '#27ae60';
          }
          function pctColor(pct) {
            if (pct >= 80) return '#27ae60';
            if (pct >= 50) return '#e67e22';
            return '#e74c3c';
          }

          return (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', fontSize: '12px', width: '100%' }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: 'left', padding: '4px 8px 4px 0', color: 'rgba(128,128,128,0.6)', fontWeight: 'normal', whiteSpace: 'nowrap', minWidth: '140px' }}>Network</th>
                    <th style={{ textAlign: 'right', padding: '4px 12px 4px 4px', color: 'rgba(128,128,128,0.6)', fontWeight: 'normal', whiteSpace: 'nowrap' }}>Coverage</th>
                    {areas.map(a => (
                      <th key={a} style={{ padding: '4px 3px', color: 'rgba(128,128,128,0.6)', fontWeight: 'normal', textAlign: 'center', fontSize: '11px', whiteSpace: 'nowrap' }}>{a}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map(({ entityId, areaMap, observed, pct }) => (
                    <tr key={entityId}>
                      <td style={{ padding: '4px 8px 4px 0', whiteSpace: 'nowrap' }}>{entityId}</td>
                      <td style={{ padding: '4px 12px 4px 4px', textAlign: 'right', fontWeight: 'bold', color: pctColor(pct) }}>{pct}%</td>
                      {areas.map(a => (
                        <td key={a} style={{ padding: '3px' }}>
                          <div style={{ background: cellColor(areaMap[a]), borderRadius: '3px', width: '20px', height: '14px', margin: '0 auto' }} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ display: 'flex', gap: '14px', marginTop: '10px', fontSize: '11px', opacity: 0.5 }}>
                <span><span style={{ display: 'inline-block', width: '10px', height: '10px', background: '#27ae60', borderRadius: '2px', verticalAlign: 'middle', marginRight: '4px' }} />observed</span>
                <span><span style={{ display: 'inline-block', width: '10px', height: '10px', background: '#e67e22', borderRadius: '2px', verticalAlign: 'middle', marginRight: '4px' }} />stale (&gt;7d)</span>
                <span><span style={{ display: 'inline-block', width: '10px', height: '10px', background: 'rgba(128,128,128,0.12)', borderRadius: '2px', verticalAlign: 'middle', marginRight: '4px' }} />never observed</span>
              </div>
            </div>
          );
        }}
      </NrqlQuery>
    );
  }
  ```

- [ ] **Step 2: Replace the Coverage placeholder in `CompareView`**

  Replace:
  ```jsx
  {subTab === 'coverage' && (
    <p style={{ opacity: 0.6 }}>Coverage coming soon…</p>
  )}
  ```
  with:
  ```jsx
  {subTab === 'coverage' && (
    <CoverageTab accountId={accountId} orgId={orgId} />
  )}
  ```

- [ ] **Step 3: Verify in browser**

  Click the Coverage pill. Table loads with networks as rows sorted descending by coverage %, config areas as columns, colored cells (green/amber/grey). Coverage % is color-coded. Legend appears below. Table scrolls horizontally if many areas.

- [ ] **Step 4: Commit**

  ```bash
  git add nerdpack/nerdlets/config-app/components/CompareView.js
  git commit -m "feat(nerdpack): add Coverage tab with heat grid to Compare"
  ```

---

### Task 3: Templates tab

**Files:**
- Modify: `nerdpack/nerdlets/config-app/components/CompareView.js`

Add a `TemplatesTab` component above `CompareView`. Replace the Templates placeholder with `<TemplatesTab>`.

The NRQL query is the same shape as `SideBySideDiff` — `latest(config_json)` faceted by `entity_id, config_area`. Client-side scoring: for each network, count config areas where its `config_json` exactly matches the template's `config_json`.

- [ ] **Step 1: Add `TemplatesTab` before `CompareView`**

  Insert the following after the closing `}` of `CoverageTab` and before `export default function CompareView`:

  ```jsx
  function TemplatesTab({ accountId, orgId }) {
    const [selectedNet, setSelectedNet] = useState(null);
    const [templateNet, setTemplateNet] = useState(null);

    const query = templateNet
      ? `SELECT latest(config_json) FROM MerakiConfigSnapshot
         WHERE org_id = '${orgId}'
         FACET entity_id, config_area
         SINCE 30 days ago LIMIT MAX`
      : null;

    return (
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px', padding: '12px', background: 'rgba(0,120,191,0.07)', border: '1px solid rgba(0,120,191,0.2)', borderRadius: '6px' }}>
          <span style={{ fontSize: '12px', opacity: 0.6, whiteSpace: 'nowrap' }}>Golden template:</span>
          <div style={{ flex: 1 }}>
            <NetworkSelector accountId={accountId} orgId={orgId} label="" value={selectedNet} onChange={setSelectedNet} />
          </div>
          <button
            onClick={() => setTemplateNet(selectedNet)}
            disabled={!selectedNet}
            style={{ padding: '6px 14px', background: selectedNet ? 'rgba(0,120,191,0.2)' : 'rgba(128,128,128,0.1)', border: `1px solid ${selectedNet ? '#0078bf' : 'rgba(128,128,128,0.3)'}`, borderRadius: '4px', color: selectedNet ? '#0078bf' : 'inherit', fontSize: '12px', cursor: selectedNet ? 'pointer' : 'not-allowed', whiteSpace: 'nowrap' }}>
            Set as Template
          </button>
        </div>

        {!templateNet && (
          <p style={{ opacity: 0.6 }}>Select a network above and click "Set as Template" to score all other networks against it.</p>
        )}

        {templateNet && query && (
          <NrqlQuery accountIds={[accountId]} query={query}>
            {({ data, loading, error }) => {
              if (loading) return <Spinner />;
              if (error) return <p style={{ color: '#c0392b' }}>Failed to load snapshot data.</p>;

              // Build map: { entityId -> { configArea -> config_json } }
              const snapshots = {};
              (data || []).forEach(s => {
                const fg = (s.metadata?.groups || []).filter(g => g.type === 'facet');
                const entityId = fg[0]?.value;
                const area = fg[1]?.value;
                if (!entityId || !area) return;
                const json = s.data?.[0]?.['latest.config_json'] ?? s.data?.[0]?.['config_json'] ?? s.data?.[0]?.json ?? null;
                if (!snapshots[entityId]) snapshots[entityId] = {};
                snapshots[entityId][area] = json;
              });

              const templateAreas = snapshots[templateNet] || {};
              const templateAreaKeys = Object.keys(templateAreas);

              if (!templateAreaKeys.length) return <p style={{ opacity: 0.6 }}>No snapshot data found for the selected template network.</p>;

              function scoreColor(pct) {
                if (pct >= 80) return { bg: 'rgba(39,174,96,0.06)', border: 'rgba(39,174,96,0.2)', text: '#27ae60' };
                if (pct >= 50) return { bg: 'rgba(230,126,34,0.06)', border: 'rgba(230,126,34,0.2)', text: '#e67e22' };
                return { bg: 'rgba(231,76,60,0.06)', border: 'rgba(231,76,60,0.2)', text: '#e74c3c' };
              }

              const scored = Object.entries(snapshots)
                .filter(([id]) => id !== templateNet)
                .map(([entityId, areaMap]) => {
                  const matched = templateAreaKeys.filter(a => areaMap[a] != null && areaMap[a] === templateAreas[a]);
                  const pct = Math.round((matched.length / templateAreaKeys.length) * 100);
                  return { entityId, areaMap, matched: new Set(matched), pct };
                })
                .sort((a, b) => b.pct - a.pct);

              return (
                <div>
                  <div style={{ marginBottom: '14px', fontSize: '12px' }}>
                    <span style={{ opacity: 0.5 }}>Scoring against: </span>
                    <span style={{ color: '#0078bf', fontWeight: 'bold' }}>{templateNet}</span>
                    <span style={{ opacity: 0.5 }}> · {templateAreaKeys.length} config areas</span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {scored.map(({ entityId, areaMap, matched, pct }) => {
                      const c = scoreColor(pct);
                      return (
                        <div key={entityId} style={{ background: c.bg, border: `1px solid ${c.border}`, borderRadius: '6px', padding: '10px 14px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                            <div style={{ flex: 1, fontSize: '13px' }}>{entityId}</div>
                            <div style={{ fontSize: '20px', fontWeight: 'bold', color: c.text }}>{pct}%</div>
                            <div style={{ fontSize: '11px', opacity: 0.5 }}>{matched.size} / {templateAreaKeys.length} areas</div>
                          </div>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                            {templateAreaKeys.map(a => (
                              <span key={a} style={{
                                fontSize: '10px', padding: '2px 7px', borderRadius: '10px',
                                background: matched.has(a) ? 'rgba(39,174,96,0.15)' : 'rgba(231,76,60,0.15)',
                                color: matched.has(a) ? '#27ae60' : '#e74c3c',
                              }}>
                                {a} {matched.has(a) ? '✓' : '✗'}
                              </span>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            }}
          </NrqlQuery>
        )}
      </div>
    );
  }
  ```

- [ ] **Step 2: Replace the Templates placeholder in `CompareView`**

  Replace:
  ```jsx
  {subTab === 'templates' && (
    <p style={{ opacity: 0.6 }}>Templates coming soon…</p>
  )}
  ```
  with:
  ```jsx
  {subTab === 'templates' && (
    <TemplatesTab accountId={accountId} orgId={orgId} />
  )}
  ```

- [ ] **Step 3: Verify in browser**

  Click the Templates pill. A "Golden template" row with dropdown and "Set as Template" button appears. Select a network, click "Set as Template". Cards appear below — one per network, showing score %, areas matched, and per-area ✓/✗ badges. Cards sorted by score descending. Template network absent from results.

- [ ] **Step 4: Commit**

  ```bash
  git add nerdpack/nerdlets/config-app/components/CompareView.js
  git commit -m "feat(nerdpack): add Templates tab with golden network scoring to Compare"
  ```

---

## Spec Coverage Checklist

- [x] Pill navigation (Networks / Coverage / Templates) — Task 1
- [x] Networks tab unchanged — Task 1
- [x] Coverage heat grid with coverage % column — Task 2
- [x] Coverage cell states (green / amber / grey) — Task 2
- [x] Coverage sorted descending by % — Task 2
- [x] Font size 12px body, 11px headers — Task 2
- [x] Single NRQL query for coverage — Task 2
- [x] Template network selector + Set button — Task 3
- [x] Scoring = exact config_json match per area — Task 3
- [x] Per-area pass/fail badges — Task 3
- [x] Score cards color-coded and sorted — Task 3
- [x] Template excluded from scored results — Task 3
