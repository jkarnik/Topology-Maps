# Site-Level Config on Network Click — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clicking a network/site row in ConfigTree selects it and loads its config areas in ConfigAreaViewer, while still toggling expand/collapse.

**Architecture:** Add two optional props (`onSelect`, `selected`) to the `TreeNode` component. When `onSelect` is provided, clicking the row calls it in addition to toggling open/closed, and applies a blue highlight when `selected` is true. Network nodes in the tree pass these props. No other files change — ConfigAreaViewer already works for any entity_id.

**Tech Stack:** React (NR1 nerdpack), `nerdpack/nerdlets/config-app/components/ConfigTree.js`

---

## File Map

| File | Change |
|------|--------|
| `nerdpack/nerdlets/config-app/components/ConfigTree.js` | Modify `TreeNode` + network render |

No other files touched.

---

### Task 1: Make network nodes selectable in ConfigTree

**Files:**
- Modify: `nerdpack/nerdlets/config-app/components/ConfigTree.js`

> **Note:** The nerdpack has no automated test runner. Verification is manual — serve locally and click a network node to confirm config loads.

- [ ] **Step 1: Update `TreeNode` to accept `onSelect` and `selected` props**

Replace the current `TreeNode` function (lines 4–17 in ConfigTree.js):

```js
function TreeNode({ label, children, defaultOpen = false, onSelect, selected }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <div
        onClick={() => { setOpen(o => !o); if (onSelect) onSelect(); }}
        style={{
          cursor: 'pointer', padding: '4px 0', fontWeight: 'bold', userSelect: 'none', fontSize: '13px',
          color: selected ? '#0078bf' : undefined,
          background: selected ? 'rgba(0,120,191,0.12)' : undefined,
          borderRadius: selected ? '3px' : undefined,
          opacity: selected ? 1 : 0.7,
        }}
      >
        {open ? '▾' : '▸'} {label}
      </div>
      {open && <div style={{ paddingLeft: '14px' }}>{children}</div>}
    </div>
  );
}
```

- [ ] **Step 2: Pass `onSelect` and `selected` to each network `TreeNode`**

In the JSX return block, find the line that renders network nodes:

```js
{networkList.map(net => (
  <TreeNode key={net.id} label={net.name || net.id} defaultOpen={networkList.length === 1}>
```

Replace it with:

```js
{networkList.map(net => (
  <TreeNode
    key={net.id}
    label={net.name || net.id}
    defaultOpen={networkList.length === 1}
    onSelect={() => onEntitySelect(net.id, 'network')}
    selected={selectedEntityId === net.id}
  >
```

- [ ] **Step 3: Verify locally**

Start the nerdpack:
```bash
cd nerdpack && nvm use 20 && nr1 nerdpack:serve --profile production
```
Open `https://one.newrelic.com/?nerdpacks=local`.

1. Select an org. The tree loads with networks listed.
2. Click a network name — the row turns blue **and** the right panel shows the network's config areas.
3. Click the same network again — it collapses (deselection of the tree node). The config panel stays (selectedEntityId persists in parent state, which is correct).
4. Click a device under a network — the right panel switches to that device's config. Clicking back to the network row restores network config.
5. Confirm the org row at the top still works as before.

- [ ] **Step 4: Commit**

```bash
git add nerdpack/nerdlets/config-app/components/ConfigTree.js
git commit -m "feat(nerdpack): clicking a network/site loads its config in ConfigAreaViewer"
```
