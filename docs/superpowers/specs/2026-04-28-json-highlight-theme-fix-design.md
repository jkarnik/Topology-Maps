# Design: JSON Highlighting — Light/Dark Mode Fix

**Date:** 2026-04-28  
**Status:** Approved

## Problem

`highlightJson` injects inline `style="color:#xxx"` attributes using VS Code Dark+ hex values. Those colors are readable on dark backgrounds but too light on light backgrounds, and too dark on dark backgrounds at certain contrast levels. They don't adapt to the user's theme.

## Goal

JSON syntax highlighting reads correctly in both light and dark mode by using CSS classes with `@media (prefers-color-scheme: dark)` overrides.

## Changes Required

### Only file: `nerdpack/nerdlets/config-app/components/ConfigAreaViewer.js`

---

## Change 1 — Update `highlightJson` to emit CSS classes

Replace inline `style="color:#xxx"` on each injected `<span>` with a `class` attribute:

| Token | Old inline style | New class |
|-------|-----------------|-----------|
| JSON key | `style="color:#9cdcfe"` | `class="json-key"` |
| String value | `style="color:#ce9178"` | `class="json-str"` |
| Number | `style="color:#b5cea8"` | `class="json-num"` |
| Boolean | `style="color:#569cd6"` | `class="json-bool"` |
| null | `style="color:#f44747"` | `class="json-null"` |

The regex logic and HTML-escape order are unchanged.

Updated return statement in `highlightJson`:
```js
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
```

---

## Change 2 — Inject `<style>` tag in `ConfigAreaViewer` render

Add a `<style>` tag as the first child of the main `<div>` returned by `ConfigAreaViewer`:

```jsx
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
```

Light mode colors (default): VS Code Light+ palette — high contrast on white/light backgrounds.  
Dark mode colors: existing VS Code Dark+ palette — unchanged from before.

The `<style>` tag is injected once per `ConfigAreaViewer` mount and applies to all `ConfigJson` instances rendered within it.

---

## Out of Scope

- No changes to tile layout, `toggleArea`, or any other component.
- No React context or props threading for theme detection — pure CSS media query.
