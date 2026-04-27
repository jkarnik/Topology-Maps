import React, { useState } from 'react';
import { Tabs, TabsItem, PlatformStateContext } from 'nr1';
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
            <OrgSelector accountId={accountId} selectedOrgId={selectedOrgId} onOrgChange={setSelectedOrgId} />
            <Tabs defaultValue="overview" style={{ marginTop: '16px' }}>
              <TabsItem value="overview" label="Overview">
                <div style={{ display: 'flex', gap: '16px', marginTop: '16px' }}>
                  <div style={{ width: '280px', flexShrink: 0 }}>
                    <ConfigTree
                      accountId={accountId}
                      orgId={selectedOrgId}
                      selectedEntityId={selectedEntityId}
                      onEntitySelect={(entityId, entityType) => {
                        setSelectedEntityId(entityId);
                        setSelectedEntityType(entityType);
                      }}
                    />
                  </div>
                  <div style={{ flex: 1 }}>
                    <ConfigAreaViewer accountId={accountId} entityId={selectedEntityId} entityType={selectedEntityType} />
                  </div>
                </div>
              </TabsItem>
              <TabsItem value="history" label="History">
                <ChangeHistory accountId={accountId} orgId={selectedOrgId} entityId={selectedEntityId} />
              </TabsItem>
              <TabsItem value="compare" label="Compare">
                <CompareView accountId={accountId} orgId={selectedOrgId} />
              </TabsItem>
            </Tabs>
          </div>
        );
      }}
    </PlatformStateContext.Consumer>
  );
}
