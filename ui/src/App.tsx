import { ReactFlowProvider } from '@xyflow/react';
import { useTopology } from './hooks/useTopology';
import { useEditMode } from './hooks/useEditMode';
import TopBar from './components/TopBar';
import TopologyCanvas from './components/TopologyCanvas';
import EditMode from './components/EditMode';
import DetailPanel from './components/DetailPanel';
import L3View from './components/L3View';

function App() {
  const {
    l2Topology,
    l3Topology,
    viewMode,
    setViewMode,
    selectedDevice,
    setSelectedDevice,
    drillDown,
    drillInto,
    drillBack,
    drillReset,
    isConnected,
    isLoading,
    pollCount,
    deviceAnimations,
    pinnedDeviceIds,
  } = useTopology();

  const {
    editMode,
    toggleEditMode,
    pendingChange,
    isApplying,
    createConnection,
    disconnectEdge,
    applyChange,
    cancelChange,
  } = useEditMode();

  return (
    <div className="h-screen flex flex-col" style={{ background: 'var(--bg-primary)' }}>
      <TopBar
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        isConnected={isConnected}
        pollCount={pollCount}
        editMode={editMode}
        onEditModeToggle={toggleEditMode}
      />
      <EditMode
        isActive={editMode}
        pendingChange={pendingChange}
        isApplying={isApplying}
        onApply={applyChange}
        onCancel={cancelChange}
      />
      <div className="flex-1 relative overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <div style={{ fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-muted)' }}>
              SCANNING NETWORK...
            </div>
          </div>
        ) : viewMode === 'l2' ? (
          <ReactFlowProvider>
            <TopologyCanvas
              topology={l2Topology}
              selectedDevice={selectedDevice}
              onSelectDevice={setSelectedDevice}
              drillDown={drillDown}
              onDrillInto={drillInto}
              onDrillBack={drillBack}
              onDrillReset={drillReset}
              editMode={editMode}
              onEditConnect={createConnection}
              onEditDisconnect={disconnectEdge}
              deviceAnimations={deviceAnimations}
              pinnedDeviceIds={pinnedDeviceIds}
            />
          </ReactFlowProvider>
        ) : (
          <ReactFlowProvider>
            <L3View topology={l3Topology} onSelectVlan={() => {}} />
          </ReactFlowProvider>
        )}

        {/* Detail panel — slides in from right when a device is selected */}
        {viewMode === 'l2' && (
          <DetailPanel
            device={selectedDevice}
            topology={l2Topology}
            onClose={() => setSelectedDevice(null)}
          />
        )}
      </div>
    </div>
  );
}

export default App;
