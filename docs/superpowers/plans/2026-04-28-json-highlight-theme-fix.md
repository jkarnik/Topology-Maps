# JSON Highlighting Light/Dark Mode Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix JSON syntax highlighting so it reads correctly in both light and dark mode using CSS classes and a `@media (prefers-color-scheme: dark)` override.

**Architecture:** Replace inline `style="color:#xxx"` in `highlightJson` with CSS class names, and inject a `<style>` tag at the top of `ConfigAreaViewer`'s render that defines light-mode colors by default and dark-mode overrides via media query.

**Tech Stack:** React (NR1 nerdpack), CSS media queries, `nerdpack/nerdlets/config-app/components/ConfigAreaViewer.js`

---

## File Map

| File | Change |
|------|--------|
| `nerdpack/nerdlets/config-app/components/ConfigAreaViewer.js` | Update `highlightJson` + add `<style>` tag |

No other files touched.

---

### Task 1: Switch to CSS classes for theme-aware JSON highlighting

**Files:**
- Modify: `nerdpack/nerdlets/config-app/components/ConfigAreaViewer.js`

> **Note:** No automated test runner for this nerdpack. Verification is manual.

- [ ] **Step 1: Update `highlightJson` to emit class names instead of inline styles**

Find the `highlightJson` function (lines 4–22). Replace the entire `.replace(...)` chain's callback — only the span-injection lines change, everything else stays identical:

**Before** (the four span-returning lines inside the callback):
```js
? `<span style="color:#9cdcfe">${match}</span>`
: `<span style="color:#ce9178">${match}</span>`;
...
if (/true|false/.test(match)) return `<span style="color:#569cd6">${match}</span>`;
if (/null/.test(match))       return `<span style="color:#f44747">${match}</span>`;
return `<span style="color:#b5cea8">${match}</span>`;
```

**After:**
```js
? `<span class="json-key">${match}</span>`
: `<span class="json-str">${match}</span>`;
...
if (/true|false/.test(match)) return `<span class="json-bool">${match}</span>`;
if (/null/.test(match))       return `<span class="json-null">${match}</span>`;
return `<span class="json-num">${match}</span>`;
```

The full updated `highlightJson` function should look like this:

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
            ? `<span class="json-key">${match}</span>`
            : `<span class="json-str">${match}</span>`;
        }
        if (/true|false/.test(match)) return `<span class="json-bool">${match}</span>`;
        if (/null/.test(match))       return `<span class="json-null">${match}</span>`;
        return `<span class="json-num">${match}</span>`;
      }
    );
}
```

- [ ] **Step 2: Add `<style>` tag as first child of `ConfigAreaViewer`'s main `<div>`**

Find the `return (` inside `ConfigAreaViewer` (around line 38). It returns a `<div>` containing an `<h3>` and a `<NrqlQuery>`. Add the `<style>` tag as the very first child:

**Before:**
```jsx
return (
  <div>
    <h3 style={{ marginBottom: '12px', fontSize: '14px' }}>
```

**After:**
```jsx
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
```

- [ ] **Step 3: Verify no inline color styles remain in `highlightJson`**

```bash
grep -n "color:#" "/Users/jkarnik/Code/Topology Maps/nerdpack/nerdlets/config-app/components/ConfigAreaViewer.js"
```

Expected: no output. Any match means a span still has an inline color style that needs to be converted to a class.

- [ ] **Step 4: Commit**

```bash
git add nerdpack/nerdlets/config-app/components/ConfigAreaViewer.js
git commit -m "fix(nerdpack): use CSS classes for JSON highlighting to support light/dark mode"
```
