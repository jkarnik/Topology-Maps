import React, { useState } from 'react';
import { PlatformStateContext } from 'nr1';
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

export default function ConfigApp() {
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
    <PlatformStateContext.Consumer>
      {(platformState) => {
        const accountId = platformState.accountId;
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
      }}
    </PlatformStateContext.Consumer>
  );
}
