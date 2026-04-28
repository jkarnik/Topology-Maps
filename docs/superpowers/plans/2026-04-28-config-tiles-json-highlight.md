# Config Area Tiles + JSON Syntax Highlighting — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the config area table with expandable tiles (multiple open at once) and add VS Code-style JSON syntax highlighting.

**Architecture:** Both changes are in `ConfigAreaViewer.js` only. Task 1 adds `highlightJson` and updates `ConfigJson`. Task 2 replaces the table and its single-selection state with a tile list and a `Set`-based multi-open state. Task 2 builds on the file state left by Task 1.

**Tech Stack:** React (NR1 nerdpack), `nerdpack/nerdlets/config-app/components/ConfigAreaViewer.js`

---

## File Map

| File | Change |
|------|--------|
| `nerdpack/nerdlets/config-app/components/ConfigAreaViewer.js` | Add `highlightJson`, update `ConfigJson`, replace table with tile list |

No other files touched.

---

### Task 1: Add `highlightJson` and update `ConfigJson` to use it

**Files:**
- Modify: `nerdpack/nerdlets/config-app/components/ConfigAreaViewer.js`

> **Note:** No automated test runner exists for this nerdpack. Verification is manual.

- [ ] **Step 1: Add `highlightJson` helper at the top of the file**

Open `nerdpack/nerdlets/config-app/components/ConfigAreaViewer.js`. After the two import lines (lines 1–2), insert this function before the `export default` line:

```js
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
            ? `<span style="color:#9cdcfe">${match}</span>`
            : `<span style="color:#ce9178">${match}</span>`;
        }
        if (/true|false/.test(match)) return `<span style="color:#569cd6">${match}</span>`;
        if (/null/.test(match))       return `<span style="color:#f44747">${match}</span>`;
        return `<span style="color:#b5cea8">${match}</span>`;
      }
    );
}
```

The regex handles: quoted keys (ending with `:`), quoted string values, `true`/`false`, `null`, and numbers. HTML escaping (`&`, `<`, `>`) runs first so angle brackets in JSON string values don't become tags.

- [ ] **Step 2: Replace the `<pre>` block in `ConfigJson` with a highlighted version**

Find the `ConfigJson` function (starts around line 78). Replace its `<pre>` element:

**Before:**
```jsx
return (
  <pre style={{
    background: 'rgba(128,128,128,0.08)', padding: '12px',
    borderRadius: '4px', overflow: 'auto', maxHeight: '400px',
    marginTop: '12px', fontSize: '12px', border: '1px solid rgba(128,128,128,0.15)',
  }}>
    {pretty}
  </pre>
);
```

**After** (remove the `pretty` variable and `try/catch` too — `highlightJson` handles both):
```jsx
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
```

Note: `marginTop: '12px'` becomes `margin: '0'` because the tile body wrapper (added in Task 2) provides its own padding. `dangerouslySetInnerHTML` is safe here — `raw` is JSON from our own NrqlQuery, not user-supplied HTML.

- [ ] **Step 3: Verify the file parses (no syntax errors)**

```bash
cd "/Users/jkarnik/Code/Topology Maps/nerdpack" && nvm use 20 && node -e "require('./nerdlets/config-app/components/ConfigAreaViewer.js')" 2>&1 | head -5
```

Expected: either silent (no output) or a module/import error about `nr1` — that's fine, it means the JS parsed correctly. A SyntaxError means something went wrong.

- [ ] **Step 4: Commit**

```bash
git add nerdpack/nerdlets/config-app/components/ConfigAreaViewer.js
git commit -m "feat(nerdpack): add JSON syntax highlighting to ConfigAreaViewer"
```

---

### Task 2: Replace table with expandable tile list

**Files:**
- Modify: `nerdpack/nerdlets/config-app/components/ConfigAreaViewer.js`

This task builds on Task 1. The file already has `highlightJson` and the updated `ConfigJson`.

- [ ] **Step 1: Replace the `useState` declaration and add `toggleArea`**

Find in `ConfigAreaViewer` (around line 5):
```js
const [selectedArea, setSelectedArea] = useState(null);
```

Replace with:
```js
const [openAreas, setOpenAreas] = useState(new Set());

function toggleArea(area) {
  setOpenAreas(prev => {
    const next = new Set(prev);
    next.has(area) ? next.delete(area) : next.add(area);
    return next;
  });
}
```

- [ ] **Step 2: Replace the entire `<table>` block and the `ConfigJson` call below it with the tile list**

Find and remove everything from `return (` inside the NrqlQuery render prop down to (and including) the closing `</>` that wraps the table and the `{selectedArea && <ConfigJson ... />}` line. Replace with:

```jsx
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
              <span style={{ opacity: 0.5, fontSize: '11px' }}>{hash.slice(0, 8)} · {ts}</span>
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
```

- [ ] **Step 3: Verify the file parses**

```bash
cd "/Users/jkarnik/Code/Topology Maps/nerdpack" && nvm use 20 && node -e "require('./nerdlets/config-app/components/ConfigAreaViewer.js')" 2>&1 | head -5
```

Expected: silent or an `nr1` import error (fine). A SyntaxError means something went wrong.

- [ ] **Step 4: Verify the complete file looks correct**

The final file should follow this structure top-to-bottom:
1. `import React, { useState } from 'react';`
2. `import { NrqlQuery, Spinner } from 'nr1';`
3. `function highlightJson(raw) { ... }` ← from Task 1
4. `export default function ConfigAreaViewer(...)` with `openAreas` Set state and tile list render
5. `function ConfigJson(...)` with `dangerouslySetInnerHTML` ← from Task 1

No `selectedArea`, no `setSelectedArea`, no `<table>`, no `<thead>`, no `<tbody>` anywhere in the file.

- [ ] **Step 5: Commit**

```bash
git add nerdpack/nerdlets/config-app/components/ConfigAreaViewer.js
git commit -m "feat(nerdpack): replace config area table with expandable tile list"
```
