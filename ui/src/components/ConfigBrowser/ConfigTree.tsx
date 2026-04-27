import React, { useState } from 'react'
import type { ConfigTree as ConfigTreeData, OrgDiffResponse } from '../../types/config'

export type TreeSelection =
  | { level: 'org'; orgId: string }
  | { level: 'network'; networkId: string }
  | { level: 'device'; entityType: string; entityId: string }

interface Props {
  orgId: string
  orgName: string
  tree: ConfigTreeData | null
  loading: boolean
  selected: TreeSelection | null
  onSelect: (sel: TreeSelection) => void
  diffResult: OrgDiffResponse | null
  showAll?: boolean
  onShowAll?: () => void
}

const MONO: React.CSSProperties = { fontFamily: "'JetBrains Mono', monospace" }

function changeCountForOrg(diff: OrgDiffResponse): number {
  return diff.results.length
}

function changeCountForNetwork(diff: OrgDiffResponse, networkId: string, deviceSerials: string[]): number {
  return diff.results.filter(r =>
    r.entity_id === networkId || deviceSerials.includes(r.entity_id)
  ).length
}

function changeCountForEntity(diff: OrgDiffResponse, entityId: string): number {
  return diff.results.filter(r => r.entity_id === entityId).length
}

const badgeStyle: React.CSSProperties = {
  fontSize: '9px',
  padding: '0 4px',
  borderRadius: '3px',
  background: 'var(--accent-amber-glow)',
  color: 'var(--accent-amber)',
  marginLeft: '6px',
  flexShrink: 0,
}

export function ConfigTree({
  orgId,
  orgName,
  tree,
  loading,
  selected,
  onSelect,
  diffResult,
  showAll = false,
  onShowAll,
}: Props) {
  const [orgOpen, setOrgOpen] = useState(true)
  const [openNetworks, setOpenNetworks] = useState<Set<string>>(new Set())

  if (loading) {
    return <div style={{ padding: '14px', fontSize: '12px', color: 'var(--text-muted)', ...MONO }}>Loading…</div>
  }
  if (!tree) {
    return <div style={{ padding: '14px', fontSize: '12px', color: 'var(--text-muted)', ...MONO }}>No data yet.</div>
  }

  const isSelected = (sel: TreeSelection): boolean => {
    if (!selected) return false
    if (sel.level !== selected.level) return false
    if (sel.level === 'org') return true
    if (sel.level === 'network' && selected.level === 'network') return sel.networkId === selected.networkId
    if (sel.level === 'device' && selected.level === 'device') return sel.entityId === selected.entityId
    return false
  }

  const rowStyle = (sel: TreeSelection, extra?: React.CSSProperties): React.CSSProperties => ({
    display: 'flex',
    alignItems: 'center',
    cursor: 'pointer',
    padding: '5px 8px',
    borderRadius: '4px',
    fontSize: '12px',
    color: isSelected(sel) ? 'var(--accent-amber)' : 'var(--text-primary)',
    background: isSelected(sel) ? 'var(--accent-amber-glow)' : 'transparent',
    fontWeight: isSelected(sel) ? 600 : 400,
    transition: 'background 0.1s ease',
    ...extra,
  })

  const hover = (sel: TreeSelection) => ({
    onMouseEnter: (e: React.MouseEvent<HTMLElement>) => {
      if (!isSelected(sel)) (e.currentTarget as HTMLElement).style.background = 'var(--bg-tertiary)'
    },
    onMouseLeave: (e: React.MouseEvent<HTMLElement>) => {
      if (!isSelected(sel)) (e.currentTarget as HTMLElement).style.background = 'transparent'
    },
  })

  const caretStyle: React.CSSProperties = {
    width: '16px',
    fontSize: '11px',
    color: 'var(--text-muted)',
    cursor: 'pointer',
    flexShrink: 0,
    userSelect: 'none',
    textAlign: 'center',
  }

  const toggleNetwork = (id: string) => {
    setOpenNetworks(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  const orgSel: TreeSelection = { level: 'org', orgId }
  const orgCount = diffResult ? changeCountForOrg(diffResult) : null

  const allNetworks = tree.networks
  const visibleNetworks = diffResult
    ? allNetworks.filter(net =>
        diffResult.results.some(r =>
          r.entity_id === net.id ||
          net.devices.some(d => r.entity_id === d.serial)
        )
      )
    : allNetworks

  return (
    <div style={{ padding: '8px 6px', overflowY: 'auto', height: '100%', ...MONO }}>

      {/* Org row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
        <span style={caretStyle} onClick={() => setOrgOpen(o => !o)}>
          {orgOpen ? '▾' : '▸'}
        </span>
        <div style={{ ...rowStyle(orgSel), flex: 1 }} onClick={() => onSelect(orgSel)} {...hover(orgSel)}>
          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 600 }}>
            {orgName}
          </span>
          {orgCount !== null && orgCount > 0 && <span style={badgeStyle}>{orgCount}</span>}
        </div>
      </div>

      {/* Networks (children of org) */}
      {orgOpen && (
        <div style={{ paddingLeft: '18px' }}>
          {visibleNetworks.length === 0 && (
            <div style={{ padding: '4px 10px', fontSize: '11px', color: 'var(--text-muted)' }}>
              {allNetworks.length === 0 ? 'No networks yet.' : 'No changed networks.'}
            </div>
          )}
          {visibleNetworks.map(net => {
            const netSel: TreeSelection = { level: 'network', networkId: net.id }
            const open = openNetworks.has(net.id)
            const deviceSerials = net.devices.map(d => d.serial)
            const netCount = diffResult ? changeCountForNetwork(diffResult, net.id, deviceSerials) : null

            return (
              <div key={net.id}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
                  <span style={caretStyle} onClick={() => toggleNetwork(net.id)}>
                    {open ? '▾' : '▸'}
                  </span>
                  <div style={{ ...rowStyle(netSel), flex: 1 }} onClick={() => onSelect(netSel)} {...hover(netSel)}>
                    <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {net.name ?? net.id}
                    </span>
                    {netCount !== null && netCount > 0 && <span style={badgeStyle}>{netCount}</span>}
                  </div>
                </div>

                {/* Devices (children of network) */}
                {open && net.devices.length > 0 && (
                  <div style={{ paddingLeft: '18px' }}>
                    {net.devices.map(dev => {
                      const devSel: TreeSelection = { level: 'device', entityType: 'device', entityId: dev.serial }
                      const devCount = diffResult ? changeCountForEntity(diffResult, dev.serial) : null
                      if (diffResult !== null && devCount === 0 && !isSelected(devSel)) return null
                      return (
                        <div
                          key={dev.serial}
                          style={rowStyle(devSel)}
                          onClick={() => onSelect(devSel)}
                          {...hover(devSel)}
                        >
                          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {dev.name ?? dev.serial}
                          </span>
                          {devCount !== null && devCount > 0 && <span style={badgeStyle}>{devCount}</span>}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}

          {/* Show all footer */}
          {diffResult && !showAll && visibleNetworks.length < allNetworks.length && (
            <div style={{ padding: '6px 8px' }}>
              <button
                style={{ fontSize: '10px', color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
                onClick={() => onShowAll?.()}
              >
                Show all networks & devices
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
