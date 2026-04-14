import React, { useMemo } from 'react';
import type { Device, DeviceType, DeviceStatus, L2Topology, Edge, DeviceInterface } from '../types/topology';

/* ---------- Props ---------- */

interface DetailPanelProps {
  device: Device | null;
  topology: L2Topology | null;
  onClose: () => void;
}

/* ---------- Helpers ---------- */

const deviceColorVar: Record<DeviceType, string> = {
  firewall: 'var(--device-firewall)',
  core_switch: 'var(--device-core-switch)',
  floor_switch: 'var(--device-floor-switch)',
  access_point: 'var(--device-ap)',
  endpoint: 'var(--device-endpoint)',
};

const statusLabel: Record<DeviceStatus, string> = {
  up: 'UP',
  down: 'DOWN',
  degraded: 'DEGRADED',
};

const statusColor: Record<DeviceStatus, string> = {
  up: 'var(--accent-green)',
  down: 'var(--accent-red)',
  degraded: 'var(--accent-amber)',
};

const statusGlow: Record<DeviceStatus, string> = {
  up: 'rgba(0, 214, 143, 0.25)',
  down: 'rgba(255, 71, 87, 0.25)',
  degraded: 'rgba(245, 166, 35, 0.25)',
};

const typeLabel: Record<DeviceType, string> = {
  firewall: 'Firewall',
  core_switch: 'Core Switch',
  floor_switch: 'Floor Switch',
  access_point: 'Access Point',
  endpoint: 'Endpoint',
};

const categoryLabel: Record<string, string> = {
  payment: 'Payment / PCI',
  operations: 'Operations',
  employee: 'Employee',
  security: 'Security',
  iot: 'IoT',
  guest: 'Guest',
};

interface Neighbor {
  device: Device;
  edge: Edge;
  localPort: string | null;
  remotePort: string | null;
}

function getNeighbors(device: Device, topology: L2Topology): Neighbor[] {
  const neighbors: Neighbor[] = [];
  for (const edge of topology.edges) {
    if (edge.source === device.id) {
      const target = topology.nodes.find((n) => n.id === edge.target);
      if (target) {
        neighbors.push({
          device: target,
          edge,
          localPort: edge.source_port,
          remotePort: edge.target_port,
        });
      }
    } else if (edge.target === device.id) {
      const source = topology.nodes.find((n) => n.id === edge.source);
      if (source) {
        neighbors.push({
          device: source,
          edge,
          localPort: edge.target_port,
          remotePort: edge.source_port,
        });
      }
    }
  }
  return neighbors;
}

function getConnectedClients(device: Device, topology: L2Topology): Device[] {
  return topology.nodes.filter(
    (n) => n.type === 'endpoint' && n.connected_ap === device.id,
  );
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
      color: 'var(--text-muted)',
      marginBottom: 8,
      marginTop: 20,
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
        fontFamily: "'DM Sans', sans-serif",
        fontSize: 12,
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
      }}
    >
      {value}
    </span>
  </div>
);

const ThroughputBar: React.FC<{ percent: number }> = ({ percent }) => {
  const clamped = Math.min(100, Math.max(0, percent));
  return (
    <div
      style={{
        width: 48,
        height: 4,
        borderRadius: 2,
        background: 'var(--bg-primary)',
        overflow: 'hidden',
        flexShrink: 0,
      }}
    >
      <div
        style={{
          width: `${clamped}%`,
          height: '100%',
          borderRadius: 2,
          background: clamped > 80 ? 'var(--accent-amber)' : 'var(--accent-cyan)',
          transition: 'width 0.3s ease',
        }}
      />
    </div>
  );
};

const InterfaceRow: React.FC<{ iface: DeviceInterface }> = ({ iface }) => {
  // Compute throughput percent based on interface speed
  const speedMbps = parseSpeedToMbps(iface.speed);
  const percent = speedMbps > 0 ? (iface.throughput_mbps / speedMbps) * 100 : 0;

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '5px 0',
        borderBottom: '1px solid var(--border-subtle)',
      }}
    >
      {/* Status dot */}
      <div
        style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: statusColor[iface.status],
          boxShadow: `0 0 4px ${statusGlow[iface.status]}`,
          flexShrink: 0,
        }}
      />
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
        {iface.name}
      </span>
      {/* Speed */}
      <span
        style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 9,
          color: 'var(--text-muted)',
          flexShrink: 0,
        }}
      >
        {iface.speed}
      </span>
      {/* Throughput bar */}
      <ThroughputBar percent={percent} />
    </div>
  );
};

function parseSpeedToMbps(speed: string): number {
  const lower = speed.toLowerCase();
  if (lower.includes('10g')) return 10000;
  if (lower.includes('5g')) return 5000;
  if (lower.includes('2.5g')) return 2500;
  if (lower.includes('1g')) return 1000;
  if (lower.includes('100m')) return 100;
  if (lower.includes('10m')) return 10;
  // Try to parse a raw number
  const num = parseFloat(speed);
  if (!isNaN(num)) return num;
  return 1000; // default fallback
}

const NeighborRow: React.FC<{ neighbor: Neighbor }> = ({ neighbor }) => (
  <div
    style={{
      padding: '6px 0',
      borderBottom: '1px solid var(--border-subtle)',
    }}
  >
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      {/* Color strip */}
      <div
        style={{
          width: 3,
          height: 24,
          borderRadius: 1.5,
          background: deviceColorVar[neighbor.device.type],
          flexShrink: 0,
        }}
      />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 11,
            fontWeight: 600,
            color: 'var(--text-primary)',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {neighbor.device.id}
        </div>
        <div
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 9,
            color: 'var(--text-muted)',
            display: 'flex',
            gap: 6,
            marginTop: 1,
          }}
        >
          {neighbor.localPort && neighbor.remotePort && (
            <span>
              {neighbor.localPort} &#8596; {neighbor.remotePort}
            </span>
          )}
          <span>{neighbor.edge.speed}</span>
        </div>
      </div>
    </div>
  </div>
);

/* ---------- PoE Section ---------- */

const PoeSection: React.FC<{ interfaces: DeviceInterface[] }> = ({ interfaces }) => {
  const totalBudget = interfaces.length * 30; // ~30W per PoE port as a default estimate
  const consumed = interfaces.reduce((sum, i) => sum + (i.poe_draw_watts ?? 0), 0);
  const remaining = Math.max(0, totalBudget - consumed);
  const percent = totalBudget > 0 ? (consumed / totalBudget) * 100 : 0;

  return (
    <>
      <SectionHeader>POE</SectionHeader>
      <InfoRow label="Budget" value={`${totalBudget}W`} />
      <InfoRow label="Consumed" value={`${consumed.toFixed(1)}W`} />
      <InfoRow label="Remaining" value={`${remaining.toFixed(1)}W`} />
      <div style={{ marginTop: 6 }}>
        <div
          style={{
            width: '100%',
            height: 6,
            borderRadius: 3,
            background: 'var(--bg-primary)',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              width: `${Math.min(100, percent)}%`,
              height: '100%',
              borderRadius: 3,
              background:
                percent > 85
                  ? 'var(--accent-red)'
                  : percent > 60
                    ? 'var(--accent-amber)'
                    : 'var(--accent-cyan)',
              transition: 'width 0.3s ease',
            }}
          />
        </div>
        <div
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 9,
            color: 'var(--text-muted)',
            textAlign: 'right',
            marginTop: 2,
          }}
        >
          {percent.toFixed(0)}%
        </div>
      </div>
    </>
  );
};

/* ---------- Wireless Section ---------- */

const WirelessSection: React.FC<{ device: Device; clients: Device[] }> = ({
  device,
  clients,
}) => {
  const MAX_SHOWN = 10;
  const shown = clients.slice(0, MAX_SHOWN);
  const remaining = clients.length - MAX_SHOWN;

  return (
    <>
      <SectionHeader>WIRELESS</SectionHeader>
      {device.ssid && <InfoRow label="SSID" value={device.ssid} />}
      <InfoRow label="Clients" value={clients.length} />

      {shown.length > 0 && (
        <div style={{ marginTop: 6 }}>
          {shown.map((client) => (
            <div
              key={client.id}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '3px 0',
                borderBottom: '1px solid var(--border-subtle)',
              }}
            >
              <span
                style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 10,
                  color: 'var(--text-primary)',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  flex: 1,
                }}
              >
                {client.id}
              </span>
              <span
                style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 9,
                  color: 'var(--text-muted)',
                  flexShrink: 0,
                  marginLeft: 8,
                }}
              >
                {client.ip}
              </span>
            </div>
          ))}
          {remaining > 0 && (
            <div
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 10,
                color: 'var(--accent-cyan)',
                marginTop: 4,
                cursor: 'pointer',
              }}
            >
              +{remaining} more...
            </div>
          )}
        </div>
      )}
    </>
  );
};

/* ---------- Close Icon ---------- */

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

/* ---------- Main Component ---------- */

const DetailPanel: React.FC<DetailPanelProps> = ({ device, topology, onClose }) => {
  const isOpen = device !== null;

  const neighbors = useMemo(() => {
    if (!device || !topology) return [];
    return getNeighbors(device, topology);
  }, [device, topology]);

  const clients = useMemo(() => {
    if (!device || !topology || device.type !== 'access_point') return [];
    return getConnectedClients(device, topology);
  }, [device, topology]);

  const isInfrastructure =
    device?.type === 'firewall' ||
    device?.type === 'core_switch' ||
    device?.type === 'floor_switch' ||
    device?.type === 'access_point';

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
          {/* Header */}
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

            {/* Device name + color strip */}
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
              <div
                style={{
                  width: 4,
                  height: 36,
                  borderRadius: 2,
                  background: deviceColorVar[device.type],
                  flexShrink: 0,
                  marginTop: 2,
                }}
              />
              <div style={{ minWidth: 0, flex: 1 }}>
                <div
                  style={{
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: 14,
                    fontWeight: 700,
                    color: 'var(--text-primary)',
                    lineHeight: 1.3,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    paddingRight: 32,
                  }}
                >
                  {device.id}
                </div>
                <div
                  style={{
                    fontFamily: "'DM Sans', sans-serif",
                    fontSize: 12,
                    color: 'var(--text-secondary)',
                    marginTop: 2,
                  }}
                >
                  {device.model}
                </div>
              </div>
            </div>

            {/* Status badge + type */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                marginTop: 10,
                marginLeft: 14,
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
                  fontFamily: "'DM Sans', sans-serif",
                  fontSize: 11,
                  color: 'var(--text-muted)',
                }}
              >
                {typeLabel[device.type]}
              </span>
            </div>
          </div>

          {/* Scrollable content */}
          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '0 16px 16px 16px',
            }}
          >
            {/* IDENTITY */}
            <SectionHeader>IDENTITY</SectionHeader>
            <InfoRow label="IP Address" value={device.ip} />
            {device.mac && <InfoRow label="MAC" value={device.mac} />}
            {device.floor != null && <InfoRow label="Floor" value={`F${device.floor}`} />}
            {device.vlan != null && <InfoRow label="VLAN" value={device.vlan} />}
            {device.category && (
              <InfoRow
                label="Category"
                value={categoryLabel[device.category] ?? device.category}
              />
            )}

            {/* INTERFACES (infrastructure only) */}
            {isInfrastructure && device.interfaces.length > 0 && (
              <>
                <SectionHeader>INTERFACES</SectionHeader>
                {device.interfaces.map((iface) => (
                  <InterfaceRow key={iface.name} iface={iface} />
                ))}
              </>
            )}

            {/* NEIGHBORS (infrastructure only) */}
            {isInfrastructure && neighbors.length > 0 && (
              <>
                <SectionHeader>NEIGHBORS</SectionHeader>
                {neighbors.map((n) => (
                  <NeighborRow key={n.edge.id} neighbor={n} />
                ))}
              </>
            )}

            {/* POE (floor switches only) */}
            {device.type === 'floor_switch' && <PoeSection interfaces={device.interfaces} />}

            {/* WIRELESS (access points only) */}
            {device.type === 'access_point' && (
              <WirelessSection device={device} clients={clients} />
            )}
          </div>
        </>
      )}
    </div>
  );
};

export default DetailPanel;
