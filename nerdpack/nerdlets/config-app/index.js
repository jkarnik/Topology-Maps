import React, { useState } from 'react';
import { PlatformStateContext, AccountsQuery } from 'nr1';
import OrgSelector from './components/OrgSelector';
import ConfigTree from './components/ConfigTree';
import ConfigAreaViewer from './components/ConfigAreaViewer';
import ChangeHistory from './components/ChangeHistory';
import CompareView from './components/CompareView';

class Catch extends React.Component {
  constructor(props) { super(props); this.state = { error: null }; }
  static getDerivedStateFromError(e) { return { error: e }; }
  render() {
    if (this.state.error) return <pre style={{ color: 'red', padding: 8, fontSize: 11 }}>{this.props.label}: {String(this.state.error)}</pre>;
    return this.props.children;
  }
}

const TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'history',  label: 'History' },
  { key: 'compare',  label: 'Compare' },
];

function ConfigAppInner({ accountId }) {
  const [selectedOrgId, setSelectedOrgId] = useState(null);
  const [selectedEntityId, setSelectedEntityId] = useState(null);
  const [selectedEntityType, setSelectedEntityType] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');

  const tabStyle = (key) => ({
    padding: '6px 16px',
    cursor: 'pointer',
    border: 'none',
    borderBottom: activeTab === key ? '2px solid #0078bf' : '2px solid transparent',
    background: 'transparent',
    color: activeTab === key ? '#0078bf' : 'inherit',
    fontWeight: activeTab === key ? 600 : 400,
    fontSize: '13px',
  });

  return (
    <div style={{ padding: '16px' }}>
      <Catch label="OrgSelector">
        <OrgSelector accountId={accountId} selectedOrgId={selectedOrgId} onOrgChange={setSelectedOrgId} />
      </Catch>

      <div style={{ display: 'flex', gap: '0', borderBottom: '1px solid rgba(128,128,128,0.2)', marginTop: '16px', marginBottom: '16px' }}>
        {TABS.map(t => (
          <button key={t.key} style={tabStyle(t.key)} onClick={() => setActiveTab(t.key)}>{t.label}</button>
        ))}
      </div>

      {activeTab === 'overview' && (
        <div style={{ display: 'flex', gap: '16px' }}>
          <div style={{ width: '280px', flexShrink: 0 }}>
            <Catch label="ConfigTree">
              <ConfigTree
                accountId={accountId}
                orgId={selectedOrgId}
                selectedEntityId={selectedEntityId}
                onEntitySelect={(entityId, entityType) => {
                  setSelectedEntityId(entityId);
                  setSelectedEntityType(entityType);
                }}
              />
            </Catch>
          </div>
          <div style={{ flex: 1 }}>
            <Catch label="ConfigAreaViewer">
              <ConfigAreaViewer accountId={accountId} entityId={selectedEntityId} entityType={selectedEntityType} />
            </Catch>
          </div>
        </div>
      )}

      {activeTab === 'history' && (
        <Catch label="ChangeHistory">
          <ChangeHistory accountId={accountId} orgId={selectedOrgId} entityId={selectedEntityId} />
        </Catch>
      )}

      {activeTab === 'compare' && (
        <Catch label="CompareView">
          <CompareView accountId={accountId} orgId={selectedOrgId} />
        </Catch>
      )}
    </div>
  );
}

function AccountPicker({ accounts }) {
  const [selectedId, setSelectedId] = useState(null);
  if (selectedId) return <ConfigAppInner accountId={selectedId} />;
  return (
    <div style={{ padding: '24px', maxWidth: '360px' }}>
      <div style={{ marginBottom: '12px', fontSize: '13px', color: '#666' }}>
        Select an account to continue:
      </div>
      {accounts.map(a => (
        <button
          key={a.id}
          onClick={() => setSelectedId(a.id)}
          style={{
            display: 'block',
            width: '100%',
            textAlign: 'left',
            padding: '10px 14px',
            marginBottom: '6px',
            borderRadius: '5px',
            border: '1px solid rgba(128,128,128,0.25)',
            background: 'transparent',
            cursor: 'pointer',
            fontSize: '13px',
          }}
        >
          <span style={{ fontWeight: 600 }}>{a.name}</span>
          <span style={{ marginLeft: '8px', color: '#999', fontSize: '11px' }}>#{a.id}</span>
        </button>
      ))}
    </div>
  );
}

export default function ConfigApp() {
  return (
    <PlatformStateContext.Consumer>
      {(platformState) => {
        const rawId = platformState.accountId;
        const resolvedId = typeof rawId === 'number'
          ? rawId
          : typeof rawId === 'string' && /^\d+$/.test(rawId)
          ? parseInt(rawId, 10)
          : null;

        if (resolvedId) {
          return <ConfigAppInner accountId={resolvedId} />;
        }

        // NR1 is in cross-account mode — resolve via AccountsQuery.
        // Single account: auto-select. Multiple accounts: show inline picker.
        return (
          <AccountsQuery>
            {({ data: accounts, loading, error }) => {
              if (loading || error || !accounts || accounts.length === 0) return null;
              if (accounts.length === 1) {
                return <ConfigAppInner accountId={accounts[0].id} />;
              }
              return <AccountPicker accounts={accounts} />;
            }}
          </AccountsQuery>
        );
      }}
    </PlatformStateContext.Consumer>
  );
}
