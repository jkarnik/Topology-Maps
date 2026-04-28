import React, { useState } from 'react';
import { Tabs, TabsItem, PlatformStateContext } from 'nr1';

class Catch extends React.Component {
  constructor(props) { super(props); this.state = { error: null }; }
  static getDerivedStateFromError(e) { return { error: e }; }
  render() {
    if (this.state.error) return <pre style={{ color: 'red', padding: 8, fontSize: 11 }}>{this.props.label}: {String(this.state.error)}</pre>;
    return this.props.children;
  }
}
import OrgSelector from './components/OrgSelector';
import ConfigTree from './components/ConfigTree';
import ConfigAreaViewer from './components/ConfigAreaViewer';
import ChangeHistory from './components/ChangeHistory';
import CompareView from './components/CompareView';

export default function ConfigApp() {
  const [selectedOrgId, setSelectedOrgId] = useState(null);
  const [selectedEntityId, setSelectedEntityId] = useState(null);
  const [selectedEntityType, setSelectedEntityType] = useState(null);

  return (
    <PlatformStateContext.Consumer>
      {(platformState) => {
        const accountId = platformState.accountId;
        return (
          <div style={{ padding: '16px' }}>
            <Catch label="OrgSelector">
              <OrgSelector accountId={accountId} selectedOrgId={selectedOrgId} onOrgChange={setSelectedOrgId} />
            </Catch>
            <Tabs defaultValue="overview" style={{ marginTop: '16px' }}>
              <TabsItem value="overview" label="Overview">
                <div style={{ display: 'flex', gap: '16px', marginTop: '16px' }}>
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
              </TabsItem>
              <TabsItem value="history" label="History">
                <Catch label="ChangeHistory">
                  <ChangeHistory accountId={accountId} orgId={selectedOrgId} entityId={selectedEntityId} />
                </Catch>
              </TabsItem>
              <TabsItem value="compare" label="Compare">
                <Catch label="CompareView">
                  <CompareView accountId={accountId} orgId={selectedOrgId} />
                </Catch>
              </TabsItem>
            </Tabs>
          </div>
        );
      }}
    </PlatformStateContext.Consumer>
  );
}
