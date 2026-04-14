import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import type { NodeProps } from '@xyflow/react';
import type { Device, DeviceType, DeviceStatus, EndpointCategory } from '../types/topology';

type DeviceNodeData = {
  device: Device;
  animationState?: 'new' | 'removing' | null;
};

/* ================================================================
   Inject keyframes + shape styles once via a <style> tag
   ================================================================ */

const STYLE_ID = 'device-node-styles';

if (typeof document !== 'undefined' && !document.getElementById(STYLE_ID)) {
  const sheet = document.createElement('style');
  sheet.id = STYLE_ID;
  sheet.textContent = `
    /* ---------- Animation: new device (green blink) ---------- */
    @keyframes device-blink-new {
      0%, 100% {
        box-shadow: var(--dn-glow);
        filter: brightness(1);
      }
      50% {
        box-shadow: 0 0 18px 4px rgba(0, 214, 143, 0.7), 0 0 6px rgba(0, 214, 143, 0.5);
        filter: brightness(1.15);
      }
    }

    /* ---------- Animation: removing device (red blink) ---------- */
    @keyframes device-blink-removing {
      0%, 100% {
        box-shadow: var(--dn-glow);
        filter: brightness(1);
      }
      50% {
        box-shadow: 0 0 18px 4px rgba(255, 71, 87, 0.7), 0 0 6px rgba(255, 71, 87, 0.5);
        filter: brightness(1.15);
      }
    }

    /* ---------- Shape: Firewall (hexagon / shield) ---------- */
    .dn-shape-firewall {
      clip-path: polygon(50% 0%, 93% 20%, 93% 70%, 50% 100%, 7% 70%, 7% 20%);
    }

    /* ---------- Shape: Access Point (circle) ---------- */
    .dn-shape-access_point {
      border-radius: 50% !important;
    }

    /* ---------- Shape: Endpoint (pill) ---------- */
    .dn-shape-endpoint {
      border-radius: 999px !important;
    }

    /* ---------- Shape: Core Switch (wide rounded rack-unit) ---------- */
    .dn-shape-core_switch {
      border-radius: 10px !important;
    }

    /* ---------- Shape: Floor Switch (standard rect with slight rounding) ---------- */
    .dn-shape-floor_switch {
      border-radius: 5px !important;
    }

    /* ---------- Shared hover behavior ---------- */
    .dn-outer:hover {
      filter: brightness(1.1);
    }

    /* ---------- Animation classes ---------- */
    .dn-anim-new {
      animation: device-blink-new 1s ease-in-out 3;
    }

    .dn-anim-removing {
      animation: device-blink-removing 1s ease-in-out 3;
    }
  `;
  document.head.appendChild(sheet);
}

/* ================================================================
   SVG icons (inline, minimal paths)
   ================================================================ */

const FirewallIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--device-firewall)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 2L3 7v6c0 5.25 3.75 10.15 9 11.25C17.25 23.15 21 18.25 21 13V7l-9-5z" />
    <path d="M12 8v4" />
    <path d="M12 16h.01" />
  </svg>
);

const CoreSwitchIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--device-core-switch)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="8" width="20" height="8" rx="2" />
    <path d="M6 12h.01" />
    <path d="M10 12h.01" />
    <path d="M14 12h.01" />
    <path d="M12 2v6M12 16v6" />
  </svg>
);

const FloorSwitchIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--device-floor-switch)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="6" width="20" height="5" rx="1.5" />
    <rect x="2" y="13" width="20" height="5" rx="1.5" />
    <circle cx="6" cy="8.5" r="0.5" fill="var(--device-floor-switch)" />
    <circle cx="6" cy="15.5" r="0.5" fill="var(--device-floor-switch)" />
  </svg>
);

const AccessPointIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--device-ap)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M5.12 19a8 8 0 0 1 0-14" />
    <path d="M18.88 5a8 8 0 0 1 0 14" />
    <path d="M8.46 16.54a5 5 0 0 1 0-9.08" />
    <path d="M15.54 7.46a5 5 0 0 1 0 9.08" />
    <circle cx="12" cy="12" r="1" fill="var(--device-ap)" />
  </svg>
);

/* ---------- Endpoint category colors ---------- */

const endpointCategoryColor: Record<EndpointCategory, string> = {
  payment: 'var(--ep-payment)',       // POS, receipt printers
  operations: 'var(--ep-operations)', // Inventory PCs, printers
  employee: 'var(--ep-employee)',     // Zebra scanners, Vocera badges
  security: 'var(--ep-security)',     // IP cameras, NVRs, access control
  iot: 'var(--ep-iot)',               // Signage, sensors, ESL
  guest: 'var(--ep-guest)',           // Customer phones, tablets
};

/* Endpoint sub-icons by category — each uses its own category color */
const PaymentIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--ep-payment)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="1" y="4" width="22" height="16" rx="2" />
    <line x1="1" y1="10" x2="23" y2="10" />
  </svg>
);

const OperationsIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--ep-operations)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="3" width="20" height="14" rx="2" />
    <line x1="8" y1="21" x2="16" y2="21" />
    <line x1="12" y1="17" x2="12" y2="21" />
  </svg>
);

const EmployeeIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--ep-employee)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="5" y="1" width="14" height="22" rx="3" />
    <line x1="12" y1="18" x2="12" y2="18.01" />
  </svg>
);

const SecurityIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--ep-security)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="10" r="7" />
    <path d="M12 17v4" />
    <path d="M8 21h8" />
    <circle cx="12" cy="10" r="2" fill="var(--ep-security)" />
  </svg>
);

const IoTIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--ep-iot)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="4" y="4" width="16" height="16" rx="2" />
    <path d="M9 9h6v6H9z" />
    <path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3" />
  </svg>
);

const GuestIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--ep-guest)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M5 12.55a11 11 0 0 1 14 0" />
    <path d="M8.53 16.11a6 6 0 0 1 6.95 0" />
    <circle cx="12" cy="20" r="1" fill="var(--ep-guest)" />
  </svg>
);

const endpointIcons: Record<EndpointCategory, React.FC> = {
  payment: PaymentIcon,
  operations: OperationsIcon,
  employee: EmployeeIcon,
  security: SecurityIcon,
  iot: IoTIcon,
  guest: GuestIcon,
};

/* ================================================================
   Helpers
   ================================================================ */

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
};

const deviceIcon: Record<Exclude<DeviceType, 'endpoint'>, React.FC> = {
  firewall: FirewallIcon,
  core_switch: CoreSwitchIcon,
  floor_switch: FloorSwitchIcon,
  access_point: AccessPointIcon,
};

const infraGlowColors: Record<DeviceType, string> = {
  firewall: 'rgba(255, 71, 87, 0.15)',
  core_switch: 'rgba(76, 154, 255, 0.15)',
  floor_switch: 'rgba(245, 166, 35, 0.15)',
  access_point: 'rgba(176, 122, 255, 0.15)',
  endpoint: 'rgba(85, 102, 119, 0.08)',
};

const categoryGlowColors: Record<EndpointCategory, string> = {
  payment: 'rgba(255, 107, 107, 0.15)',
  operations: 'rgba(78, 205, 196, 0.15)',
  employee: 'rgba(69, 183, 209, 0.15)',
  security: 'rgba(247, 183, 49, 0.15)',
  iot: 'rgba(38, 222, 129, 0.15)',
  guest: 'rgba(165, 94, 234, 0.15)',
};

function getGlowShadow(type: DeviceType, category?: EndpointCategory | null): string {
  const glowColor = type === 'endpoint' && category
    ? categoryGlowColors[category]
    : infraGlowColors[type];
  return `0 2px 14px ${glowColor}, 0 1px 3px rgba(0,0,0,0.4)`;
}

function getHoverGlowShadow(type: DeviceType, category?: EndpointCategory | null): string {
  const glowColor = type === 'endpoint' && category
    ? categoryGlowColors[category]!.replace('0.15)', '0.35)')
    : infraGlowColors[type].replace('0.15)', '0.35)').replace('0.08)', '0.2)');
  return `0 4px 24px ${glowColor}, 0 1px 4px rgba(0,0,0,0.5)`;
}

/* ---------- Per-shape sizing and layout config ---------- */

interface ShapeConfig {
  /** Total outer width of the shape container */
  width: number;
  /** Total outer height of the shape container */
  height: number;
  /** Padding inside the colored shape for the content area */
  contentPadding: string;
  /** Extra offset for labels to avoid clip-path cropping */
  labelInset?: number;
}

const shapeConfigs: Record<DeviceType, ShapeConfig> = {
  firewall: { width: 180, height: 190, contentPadding: '38px 24px 30px', labelInset: 8 },
  core_switch: { width: 220, height: 80, contentPadding: '12px 18px' },
  floor_switch: { width: 190, height: 90, contentPadding: '12px 16px' },
  access_point: { width: 130, height: 130, contentPadding: '26px 16px' },
  endpoint: { width: 140, height: 48, contentPadding: '8px 18px' },
};

/* ================================================================
   Component
   ================================================================ */

const DeviceNode = memo(({ data }: NodeProps) => {
  const { device, animationState } = data as DeviceNodeData;
  const { type, status, id } = device;
  // Endpoints use their category color; infrastructure uses device type color
  const color = type === 'endpoint' && device.category
    ? endpointCategoryColor[device.category]
    : deviceColorVar[type];
  const cfg = shapeConfigs[type];
  const tiny = type === 'endpoint';
  const isCircle = type === 'access_point';
  const isHex = type === 'firewall';

  const Icon =
    type === 'endpoint'
      ? endpointIcons[device.category ?? 'operations']
      : deviceIcon[type];

  /* Build animation class name */
  let animClass = '';
  if (animationState === 'new') animClass = ' dn-anim-new';
  if (animationState === 'removing') animClass = ' dn-anim-removing';

  /* Border accent color for the shape */
  const borderAccent = `2px solid ${color}`;

  return (
    <div
      style={{
        /* Use this wrapper purely for React Flow positioning — no visual style */
        position: 'relative',
        width: cfg.width,
        height: cfg.height,
        fontFamily: "'JetBrains Mono', monospace",
      }}
    >
      {/* Connection handles — positioned at the midpoints of the bounding box */}
      <Handle
        type="target"
        position={Position.Top}
        style={{
          width: 6,
          height: 6,
          background: color,
          border: 'none',
          opacity: 0,
        }}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        style={{
          width: 6,
          height: 6,
          background: color,
          border: 'none',
          opacity: 0,
        }}
      />

      {/* ---------- Shaped outer container ---------- */}
      <div
        className={`dn-outer dn-shape-${type}${animClass}`}
        style={{
          '--dn-glow': getGlowShadow(type, device.category),
          width: '100%',
          height: '100%',
          background: 'var(--bg-elevated)',
          border: borderAccent,
          boxShadow: getGlowShadow(type, device.category),
          cursor: 'pointer',
          transition: 'box-shadow 0.2s ease, filter 0.2s ease',
          display: 'flex',
          flexDirection: 'column',
          alignItems: isCircle || isHex ? 'center' : 'flex-start',
          justifyContent: 'center',
          padding: cfg.contentPadding,
          position: 'relative',
          overflow: isHex ? 'visible' : 'hidden',
        } as React.CSSProperties}
        onMouseEnter={(e) => {
          const el = e.currentTarget;
          el.style.boxShadow = getHoverGlowShadow(type, device.category);
        }}
        onMouseLeave={(e) => {
          const el = e.currentTarget;
          el.style.boxShadow = getGlowShadow(type, device.category);
        }}
      >
        {/* Status indicator dot */}
        {!isHex && (
          <div
            style={{
              position: 'absolute',
              top: isCircle ? 14 : 8,
              right: isCircle ? 14 : 8,
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: statusColor[status],
              boxShadow: `0 0 6px ${statusColor[status]}`,
              zIndex: 2,
            }}
          />
        )}

        {/* ---------- Content layout ---------- */}
        {isCircle ? (
          /* Access Point: centered circle layout */
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, textAlign: 'center' }}>
            <Icon />
            <div
              style={{
                fontSize: 11,
                fontWeight: 600,
                color: 'var(--text-primary)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                maxWidth: cfg.width - 40,
                lineHeight: 1.3,
              }}
            >
              {id}
            </div>
            <div
              style={{
                fontSize: 9,
                color: 'var(--text-muted)',
                fontFamily: "'JetBrains Mono', monospace",
                whiteSpace: 'nowrap',
                lineHeight: 1.3,
              }}
            >
              {device.ip}
            </div>
          </div>
        ) : isHex ? (
          /* Firewall: centered hexagonal layout */
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, textAlign: 'center' }}>
            {/* Status dot for hexagon — placed above the icon */}
            <div
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: statusColor[status],
                boxShadow: `0 0 6px ${statusColor[status]}`,
                marginBottom: 2,
              }}
            />
            <Icon />
            <div
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: 'var(--text-primary)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                maxWidth: cfg.width - 60,
                lineHeight: 1.3,
              }}
            >
              {id}
            </div>
            <div
              style={{
                fontSize: 10,
                color: 'var(--text-secondary)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                maxWidth: cfg.width - 60,
                lineHeight: 1.3,
              }}
            >
              {device.model}
            </div>
            <div
              style={{
                fontSize: 10,
                color: 'var(--text-muted)',
                fontFamily: "'JetBrains Mono', monospace",
                whiteSpace: 'nowrap',
                lineHeight: 1.3,
              }}
            >
              {device.ip}
            </div>
          </div>
        ) : tiny ? (
          /* Endpoint: compact pill layout, horizontal row */
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%' }}>
            <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Icon />
            </div>
            <div style={{ minWidth: 0, overflow: 'hidden' }}>
              <div
                style={{
                  fontSize: 10,
                  fontWeight: 600,
                  color: 'var(--text-primary)',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  lineHeight: 1.3,
                }}
              >
                {id}
              </div>
              <div
                style={{
                  fontSize: 9,
                  color: 'var(--text-muted)',
                  fontFamily: "'JetBrains Mono', monospace",
                  whiteSpace: 'nowrap',
                  lineHeight: 1.3,
                  marginTop: 1,
                }}
              >
                {device.ip}
              </div>
            </div>
            {/* Status dot inside pill */}
            <div
              style={{
                marginLeft: 'auto',
                flexShrink: 0,
                width: 7,
                height: 7,
                borderRadius: '50%',
                background: statusColor[status],
                boxShadow: `0 0 5px ${statusColor[status]}`,
              }}
            />
          </div>
        ) : (
          /* Core Switch / Floor Switch: horizontal row layout */
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, width: '100%' }}>
            <div style={{ flexShrink: 0, marginTop: 2, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Icon />
            </div>
            <div style={{ minWidth: 0, overflow: 'hidden' }}>
              <div
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: 'var(--text-primary)',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  lineHeight: 1.3,
                  paddingRight: 14,
                }}
              >
                {id}
              </div>
              <div
                style={{
                  fontSize: 10,
                  color: 'var(--text-secondary)',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  lineHeight: 1.4,
                  marginTop: 1,
                }}
              >
                {device.model}
              </div>
              <div
                style={{
                  fontSize: 10,
                  color: 'var(--text-muted)',
                  fontFamily: "'JetBrains Mono', monospace",
                  whiteSpace: 'nowrap',
                  lineHeight: 1.4,
                  marginTop: 2,
                }}
              >
                {device.ip}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Floor badge for floor switches */}
      {type === 'floor_switch' && device.floor != null && (
        <div
          style={{
            position: 'absolute',
            top: -8,
            right: -8,
            background: 'var(--device-floor-switch)',
            color: 'var(--bg-primary)',
            fontSize: 9,
            fontWeight: 700,
            width: 22,
            height: 22,
            borderRadius: '50%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 2px 8px rgba(245, 166, 35, 0.5)',
            lineHeight: 1,
            zIndex: 3,
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          F{device.floor}
        </div>
      )}
    </div>
  );
});

DeviceNode.displayName = 'DeviceNode';

export default DeviceNode;
