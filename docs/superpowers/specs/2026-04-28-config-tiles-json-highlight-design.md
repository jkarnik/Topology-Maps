# Design: Config Area Tiles + JSON Syntax Highlighting

**Date:** 2026-04-28  
**Status:** Approved

## Problem

`ConfigAreaViewer` currently shows config areas as a table. Clicking a row opens a single JSON panel at the bottom — only one area visible at a time, and the JSON is plain unstyled text.

## Goal

1. Replace the table with a vertical list of expandable tiles — multiple can be open simultaneously.
2. Add VS Code-style syntax highlighting to all JSON output.

## Changes Required

### Only file: `nerdpack/nerdlets/config-app/components/ConfigAreaViewer.js`

---

## Feature 1 — Tile List Layout

**State:** Replace `const [selectedArea, setSelectedArea] = useState(null)` with `const [openAreas, setOpenAreas] = useState(new Set())`. A tile is open when its area name is in the Set.

**Toggle logic:**
```js
function toggleArea(area) {
  setOpenAreas(prev => {
    const next = new Set(prev);
    next.has(area) ? next.delete(area) : next.add(area);
    return next;
  });
}
```

**Tile structure** (replaces the `<table>`):
```
<div>  ← outer list container, display:flex flex-direction:column gap:6px
  <div onClick={() => toggleArea(area)}>  ← tile
    <div>  ← tile header: name + hash + timestamp + chevron
    <div>  ← tile body (only rendered when area is in openAreas)
      <ConfigJson ... />
  </div>
```

**Tile header styles:**
- Default: `background: rgba(128,128,128,0.05)`, `border: 1px solid rgba(128,128,128,0.2)`, `border-radius: 6px`
- Open: `background: rgba(0,120,191,0.12)`, `color: #0078bf`
- Chevron: `▶` rotated 90° when open, `opacity: 0.4` when closed, `opacity: 1` + `color: #0078bf` when open

**Tile body:** rendered (not just hidden) only when open — avoids unnecessary NrqlQuery calls for collapsed tiles. The existing `ConfigJson` component is reused unchanged.

---

## Feature 2 — JSON Syntax Highlighting

**New helper function** `highlightJson(raw)` — added at module level in `ConfigAreaViewer.js`:

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

**HTML escaping** (`&`, `<`, `>`) runs before the regex so angle brackets in JSON string values don't break the injected spans.

**Usage in `ConfigJson`:** Replace the current `<pre>` block with:
```jsx
<pre
  style={{ background: 'rgba(128,128,128,0.08)', padding: '12px', borderRadius: '4px',
           overflow: 'auto', maxHeight: '400px', marginTop: '0', fontSize: '12px',
           border: '1px solid rgba(128,128,128,0.15)', fontFamily: 'monospace', lineHeight: '1.6' }}
  dangerouslySetInnerHTML={{ __html: highlightJson(raw) }}
/>
```

`dangerouslySetInnerHTML` is safe here: `raw` is JSON from our own NrqlQuery, not user-supplied HTML. The HTML-escape step above prevents any embedded angle brackets from becoming tags.

---

## Out of Scope

- No changes to `ChangeHistory`, `CompareView`, `DiffViewer`, `ConfigTree`, or `index.js`.
- No changes to the backend or `config_ingest.py`.
- No copy-to-clipboard or expand-all button (not requested).
