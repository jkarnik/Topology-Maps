import React, { useEffect, useState } from 'react';
import type { Device, DeviceType, DeviceStatus, L2Topology, Edge } from '../types/topology';

/* ---------- Props ---------- */

interface MerakiDetailPanelProps {
  device: Device | null;
  topology: L2Topology | null;
  clientCounts: Record<string, number>;
  onClose: () => void;
  /**
   * Resolve per-device detail (clients + switch ports).  The parent hook
   * pre-populates this during refresh, so selection typically completes
   * without any additional Meraki API calls.  When the cache lacks an
   * entry — e.g. a new device since the last refresh — the resolver
   * falls back to a live fetch.
   */
  onGetDeviceDetail: (serial: string) => Promise<{
    serial: string;
    clients: Record<string, unknown>[];
    switch_ports: Record<string, unknown>[];
  } | null>;
}

/* ---------- API types ---------- */

interface ApiClient {
  description?: string;
  mac?: string;
  ip?: string;
  ip6?: string;
}

interface ApiSwitchPort {
  portId?: string;
  name?: string;
  type?: string;
  vlan?: number;
}

interface DeviceDetail {
  serial: string;
  clients: ApiClient[];
  switch_ports: ApiSwitchPort[];
}

/* ---------- Helpers ---------- */

const deviceColorVar: Record<DeviceType, string> = {
  firewall: 'var(--device-firewall)',
  core_switch: 'var(--device-core-switch)',
  floor_switch: 'var(--device-floor-switch)',
  access_point: 'var(--device-ap)',
  endpoint: 'var(--device-endpoint)',
};

const statusColor: Record<DeviceStatus, string> = {
  up: 'var(--accent-green)',
  down: 'var(--accent-red)',
  degraded: 'var(--accent-amber)',
  alerting: 'var(--accent-amber)',
};

const statusGlow: Record<DeviceStatus, string> = {
  up: 'rgba(0, 214, 143, 0.25)',
  down: 'rgba(255, 71, 87, 0.25)',
  degraded: 'rgba(245, 166, 35, 0.25)',
  alerting: 'rgba(245, 166, 35, 0.25)',
};

const statusLabel: Record<DeviceStatus, string> = {
  up: 'UP',
  down: 'DOWN',
  degraded: 'DEGRADED',
  alerting: 'ALERTING',
};

const typeLabel: Record<DeviceType, string> = {
  firewall: 'Firewall',
  core_switch: 'Core Switch',
  floor_switch: 'Floor Switch',
  access_point: 'Access Point',
  endpoint: 'Endpoint',
};

interface Neighbor {
  neighborId: string;
  localPort: string | null;
  protocol: string;
  edge: Edge;
}

function getNeighbors(device: Device, topology: L2Topology): Neighbor[] {
  const neighbors: Neighbor[] = [];
  for (const edge of topology.edges) {
    if (edge.source === device.id) {
      neighbors.push({
        neighborId: edge.target,
        localPort: edge.source_port,
        protocol: edge.protocol,
        edge,
      });
    } else if (edge.target === device.id) {
      neighbors.push({
        neighborId: edge.source,
        localPort: edge.target_port,
        protocol: edge.protocol,
        edge,
      });
    }
  }
  return neighbors;
}

/* ---------- Sub-components ---------- */

const SectionHeader: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div
    style={{
      fontFamily: "'JetBrains Mono', monospace",
      fontSize: 10,
      fontWeight: 600,
      letterSpacing: '0.14em',
      textTransform: 'uppercase',
      color: 'var(--accent-amber)',
      marginBottom: 8,
      marginTop: 20,
      paddingBottom: 4,
      borderBottom: '1px solid var(--border-subtle)',
    }}
  >
    {children}
  </div>
);

const InfoRow: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div
    style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: '4px 0',
    }}
  >
    <span
      style={{
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 11,
        color: 'var(--text-secondary)',
      }}
    >
      {label}
    </span>
    <span
      style={{
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 11,
        color: 'var(--text-primary)',
        textAlign: 'right',
        maxWidth: '60%',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}
    >
      {value}
    </span>
  </div>
);

const CloseIcon: React.FC = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

/* ---------- Loading spinner ---------- */

const Spinner: React.FC = () => (
  <div
    style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '20px 0',
    }}
  >
    <div
      style={{
        width: 20,
        height: 20,
        border: '2px solid var(--border-subtle)',
        borderTopColor: 'var(--accent-amber)',
        borderRadius: '50%',
        animation: 'spin 0.7s linear infinite',
      }}
    />
    <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
  </div>
);

/* ---------- Main Component ---------- */

const MerakiDetailPanel: React.FC<MerakiDetailPanelProps> = ({
  device,
  topology,
  clientCounts,
  onClose,
  onGetDeviceDetail,
}) => {
  const isOpen = device !== null;
  const [detail, setDetail] = useState<DeviceDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Resolve device detail whenever the selected device changes.  The
  // resolver checks the in-memory cache populated during refresh before
  // falling back to a network call, so clicks are typically instant.
  useEffect(() => {
    if (!device) {
      setDetail(null);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    setDetail(null);

    onGetDeviceDetail(device.id)
      .then((data) => {
        if (cancelled) return;
        if (data) {
          setDetail(data as DeviceDetail);
        } else {
          setError('Device detail unavailable');
        }
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load device detail');
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [device?.id, onGetDeviceDetail]);

  // Neighbors from topology
  const neighbors = React.useMemo(() => {
    if (!device || !topology) return [];
    return getNeighbors(device, topology);
  }, [device, topology]);

  const clientCount = device ? (clientCounts[device.id] ?? 0) : 0;
  const isSwitch = device?.type === 'floor_switch' || device?.type === 'core_switch';

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        right: 0,
        width: 320,
        height: '100%',
        background: 'var(--bg-secondary)',
        borderLeft: '1px solid var(--border-subtle)',
        transform: isOpen ? 'translateX(0)' : 'translateX(100%)',
        transition: 'transform 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
        zIndex: 30,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {device && (
        <>
          {/* ---- Header ---- */}
          <div
            style={{
              padding: '16px 16px 12px 16px',
              borderBottom: '1px solid var(--border-subtle)',
              flexShrink: 0,
            }}
          >
            {/* Close button */}
            <button
              onClick={onClose}
              style={{
                position: 'absolute',
                top: 12,
                right: 12,
                width: 28,
                height: 28,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: '1px solid var(--border-subtle)',
                borderRadius: 4,
                background: 'transparent',
                color: 'var(--text-muted)',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.color = 'var(--text-primary)';
                e.currentTarget.style.borderColor = 'var(--text-secondary)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.color = 'var(--text-muted)';
                e.currentTarget.style.borderColor = 'var(--border-subtle)';
              }}
            >
              <CloseIcon />
            </button>

            {/* Status dot + device name + color strip */}
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
              {/* Left color strip by device type */}
              <div
                style={{
                  width: 4,
                  height: 42,
                  borderRadius: 2,
                  background: deviceColorVar[device.type],
                  flexShrink: 0,
                  marginTop: 2,
                }}
              />

              <div style={{ flex: 1, minWidth: 0 }}>
                {/* Status dot + device ID */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, paddingRight: 32 }}>
                  <span
                    className="animate-pulse-dot"
                    style={{
                      display: 'inline-block',
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: statusColor[device.status],
                      boxShadow: `0 0 6px ${statusGlow[device.status]}`,
                      flexShrink: 0,
                    }}
                  />
                  <span
                    style={{
                      fontFamily: "'JetBrains Mono', monospace",
                      fontSize: 13,
                      fontWeight: 700,
                      color: 'var(--text-primary)',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {device.name || device.id}
                  </span>
                </div>

                {/* Model */}
                <div
                  style={{
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: 11,
                    color: 'var(--text-secondary)',
                    marginTop: 3,
                  }}
                >
                  {device.model}
                </div>

                {/* IP + MAC */}
                <div
                  style={{
                    display: 'flex',
                    gap: 10,
                    marginTop: 4,
                    flexWrap: 'wrap',
                  }}
                >
                  <span
                    style={{
                      fontFamily: "'JetBrains Mono', monospace",
                      fontSize: 10,
                      color: 'var(--text-muted)',
                    }}
                  >
                    {device.ip}
                  </span>
                  {device.mac && (
                    <span
                      style={{
                        fontFamily: "'JetBrains Mono', monospace",
                        fontSize: 10,
                        color: 'var(--text-muted)',
                      }}
                    >
                      {device.mac}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Status badge + type label + client count */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                marginTop: 10,
                marginLeft: 14,
                flexWrap: 'wrap',
              }}
            >
              <span
                style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: '0.08em',
                  padding: '2px 8px',
                  borderRadius: 3,
                  background: statusGlow[device.status],
                  color: statusColor[device.status],
                  border: `1px solid ${statusColor[device.status]}`,
                }}
              >
                {statusLabel[device.status]}
              </span>
              <span
                style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 10,
                  color: 'var(--text-muted)',
                }}
              >
                {typeLabel[device.type]}
              </span>
              {clientCount > 0 && (
                <span
                  style={{
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: 10,
                    color: 'var(--accent-amber)',
                    marginLeft: 'auto',
                    paddingRight: 4,
                  }}
                >
                  {clientCount} clients
                </span>
              )}
            </div>
          </div>

          {/* ---- Scrollable body ---- */}
          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '0 16px 24px 16px',
            }}
          >
            {loading && <Spinner />}

            {error && (
              <div
                style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 10,
                  color: 'var(--accent-red)',
                  marginTop: 16,
                  padding: '8px 10px',
                  background: 'rgba(255, 71, 87, 0.08)',
                  borderRadius: 4,
                  border: '1px solid rgba(255, 71, 87, 0.2)',
                }}
              >
                {error}
              </div>
            )}

            {/* ---- Identity ---- */}
            {!loading && (
              <>
                <SectionHeader>Identity</SectionHeader>
                {device.name && device.name !== device.id && <InfoRow label="Name" value={device.name} />}
                <InfoRow label="Serial" value={device.id} />
                <InfoRow label="Model" value={device.model} />
                {device.software_version && <InfoRow label="Software" value={device.software_version} />}
                {device.firmware && <InfoRow label="Firmware" value={device.firmware} />}
                {device.network_id && <InfoRow label="Network ID" value={device.network_id} />}
                {device.stack_name && (
                  <InfoRow
                    label="Stack"
                    value={`${device.stack_name}${device.stack_role ? ` (${device.stack_role})` : ''}`}
                  />
                )}

                <SectionHeader>Network</SectionHeader>
                <InfoRow label="IP" value={device.ip || '—'} />
                {device.public_ip && <InfoRow label="Public IP" value={device.public_ip} />}
                {device.mac && <InfoRow label="MAC" value={device.mac} />}
                {device.gateway && <InfoRow label="Gateway" value={device.gateway} />}
                {device.primary_dns && <InfoRow label="Primary DNS" value={device.primary_dns} />}
                {device.secondary_dns && <InfoRow label="Secondary DNS" value={device.secondary_dns} />}
                {device.ip_type && <InfoRow label="IP Type" value={device.ip_type} />}
                {device.vlan != null && <InfoRow label="VLAN" value={device.vlan} />}
                {device.ssid && <InfoRow label="SSID" value={device.ssid} />}
                {device.floor != null && <InfoRow label="Floor" value={`F${device.floor}`} />}

                {device.address && (
                  <>
                    <SectionHeader>Location</SectionHeader>
                    <InfoRow label="Address" value={device.address} />
                  </>
                )}

                {(device.tags?.length || device.notes || device.config_updated_at || device.dashboard_url) && (
                  <>
                    <SectionHeader>Meta</SectionHeader>
                    {device.tags && device.tags.length > 0 && (
                      <InfoRow label="Tags" value={device.tags.join(', ')} />
                    )}
                    {device.notes && <InfoRow label="Notes" value={device.notes} />}
                    {device.config_updated_at && (
                      <InfoRow label="Config Updated" value={new Date(device.config_updated_at).toLocaleString()} />
                    )}
                    {device.dashboard_url && (
                      <InfoRow
                        label="Dashboard"
                        value={
                          <a
                            href={device.dashboard_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ color: 'var(--accent-amber)', textDecoration: 'none' }}
                          >
                            Open ↗
                          </a>
                        }
                      />
                    )}
                  </>
                )}
              </>
            )}

            {/* ---- Clients (from API) ---- */}
            {detail && detail.clients.length > 0 && (
              <>
                <SectionHeader>Clients</SectionHeader>
                {detail.clients.slice(0, 20).map((c, i) => (
                  <div
                    key={c.mac ?? i}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                      padding: '5px 0',
                      borderBottom: '1px solid var(--border-subtle)',
                      gap: 8,
                    }}
                  >
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div
                        style={{
                          fontFamily: "'JetBrains Mono', monospace",
                          fontSize: 10,
                          color: 'var(--text-primary)',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {c.description || c.mac || 'Unknown'}
                      </div>
                      {c.mac && c.description && (
                        <div
                          style={{
                            fontFamily: "'JetBrains Mono', monospace",
                            fontSize: 9,
                            color: 'var(--text-muted)',
                            marginTop: 1,
                          }}
                        >
                          {c.mac}
                        </div>
                      )}
                    </div>
                    <span
                      style={{
                        fontFamily: "'JetBrains Mono', monospace",
                        fontSize: 10,
                        color: 'var(--text-secondary)',
                        flexShrink: 0,
                      }}
                    >
                      {c.ip ?? c.ip6 ?? '—'}
                    </span>
                  </div>
                ))}
                {detail.clients.length > 20 && (
                  <div
                    style={{
                      fontFamily: "'JetBrains Mono', monospace",
                      fontSize: 10,
                      color: 'var(--accent-amber)',
                      marginTop: 6,
                    }}
                  >
                    +{detail.clients.length - 20} more
                  </div>
                )}
              </>
            )}

            {/* ---- Ports (switches only) ---- */}
            {detail && isSwitch && detail.switch_ports.length > 0 && (
              <>
                <SectionHeader>Ports</SectionHeader>
                {detail.switch_ports.map((port, i) => (
                  <div
                    key={port.portId ?? i}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      padding: '5px 0',
                      borderBottom: '1px solid var(--border-subtle)',
                    }}
                  >
                    {/* Port ID chip */}
                    <span
                      style={{
                        fontFamily: "'JetBrains Mono', monospace",
                        fontSize: 9,
                        fontWeight: 600,
                        background: 'var(--bg-tertiary)',
                        color: 'var(--text-secondary)',
                        padding: '2px 6px',
                        borderRadius: 3,
                        flexShrink: 0,
                        minWidth: 28,
                        textAlign: 'center',
                      }}
                    >
                      {port.portId ?? '?'}
                    </span>

                    {/* Name */}
                    <span
                      style={{
                        fontFamily: "'JetBrains Mono', monospace",
                        fontSize: 10,
                        color: 'var(--text-primary)',
                        flex: 1,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {port.name || '—'}
                    </span>

                    {/* Type */}
                    {port.type && (
                      <span
                        style={{
                          fontFamily: "'JetBrains Mono', monospace",
                          fontSize: 9,
                          color: 'var(--text-muted)',
                          flexShrink: 0,
                        }}
                      >
                        {port.type}
                      </span>
                    )}

                    {/* VLAN */}
                    {port.vlan != null && (
                      <span
                        style={{
                          fontFamily: "'JetBrains Mono', monospace",
                          fontSize: 9,
                          color: 'var(--accent-amber)',
                          flexShrink: 0,
                        }}
                      >
                        v{port.vlan}
                      </span>
                    )}
                  </div>
                ))}
              </>
            )}

            {/* ---- Neighbors (from topology edges) ---- */}
            {neighbors.length > 0 && (
              <>
                <SectionHeader>Neighbors</SectionHeader>
                {neighbors.map((n) => (
                  <div
                    key={n.edge.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      padding: '6px 0',
                      borderBottom: '1px solid var(--border-subtle)',
                    }}
                  >
                    {/* Port label */}
                    <span
                      style={{
                        fontFamily: "'JetBrains Mono', monospace",
                        fontSize: 9,
                        background: 'var(--bg-tertiary)',
                        color: 'var(--text-secondary)',
                        padding: '2px 6px',
                        borderRadius: 3,
                        flexShrink: 0,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {n.localPort ?? 'port'}
                    </span>

                    <span
                      style={{
                        fontFamily: "'JetBrains Mono', monospace",
                        fontSize: 9,
                        color: 'var(--text-muted)',
                        flexShrink: 0,
                      }}
                    >
                      &#8594;
                    </span>

                    {/* Neighbor ID */}
                    <span
                      style={{
                        fontFamily: "'JetBrains Mono', monospace",
                        fontSize: 10,
                        color: 'var(--text-primary)',
                        flex: 1,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {n.neighborId}
                    </span>

                    {/* Protocol badge */}
                    <span
                      style={{
                        fontFamily: "'JetBrains Mono', monospace",
                        fontSize: 9,
                        color: 'var(--accent-amber)',
                        flexShrink: 0,
                        letterSpacing: '0.05em',
                      }}
                    >
                      {n.protocol}
                    </span>
                  </div>
                ))}
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
};

export default MerakiDetailPanel;
