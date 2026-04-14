import { ReactFlowProvider } from '@xyflow/react';
import { useTopology } from './hooks/useTopology';
import TopBar from './components/TopBar';
import TopologyCanvas from './components/TopologyCanvas';
import DetailPanel from './components/DetailPanel';
import L3View from './components/L3View';
import HybridView from './components/HybridView';

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

  return (
    <div className="h-screen flex flex-col" style={{ background: 'var(--bg-primary)' }}>
      <TopBar
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        isConnected={isConnected}
        pollCount={pollCount}
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
              deviceAnimations={deviceAnimations}
              pinnedDeviceIds={pinnedDeviceIds}
            />
          </ReactFlowProvider>
        ) : viewMode === 'hybrid' ? (
          <ReactFlowProvider>
            <HybridView
              l2Topology={l2Topology}
              l3Topology={l3Topology}
              onSelectDevice={setSelectedDevice}
              onSelectVlan={() => {}}
            />
          </ReactFlowProvider>
        ) : (
          <ReactFlowProvider>
            <L3View topology={l3Topology} onSelectVlan={() => {}} />
          </ReactFlowProvider>
        )}

        {/* Detail panel — slides in from right when a device is selected */}
        {(viewMode === 'l2' || viewMode === 'hybrid') && (
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
