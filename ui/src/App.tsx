import { useState, useEffect } from 'react';
import { ReactFlowProvider } from '@xyflow/react';
import { useTopology } from './hooks/useTopology';
import { useSimulation } from './hooks/useSimulation';
import { useMerakiTopology } from './hooks/useMerakiTopology';
import TopBar from './components/TopBar';
import TopologyCanvas from './components/TopologyCanvas';
import DetailPanel from './components/DetailPanel';
import MerakiDetailPanel from './components/MerakiDetailPanel';
import RefreshOverlay from './components/RefreshOverlay';
import L3View from './components/L3View';
import HybridView from './components/HybridView';
import type { DataSource } from './types/topology';

function App() {
  const [dataSource, setDataSource] = useState<DataSource>('simulated');
  const sim = useSimulation();
  const topo = useTopology();
  const meraki = useMerakiTopology();

  // First-switch trigger for Meraki
  const [merakiInitialized, setMerakiInitialized] = useState(false);
  useEffect(() => {
    if (dataSource === 'meraki' && !merakiInitialized) {
      setMerakiInitialized(true);
      meraki.refresh();
    }
  }, [dataSource, merakiInitialized]);

  const isSimulated = dataSource === 'simulated';
  const l2 = isSimulated ? topo.l2Topology : meraki.l2Topology;
  const l3 = isSimulated ? topo.l3Topology : meraki.l3Topology;
  const viewMode = isSimulated ? topo.viewMode : meraki.viewMode;
  const setViewMode = isSimulated ? topo.setViewMode : meraki.setViewMode;
  const selectedDevice = isSimulated ? topo.selectedDevice : meraki.selectedDevice;
  const setSelectedDevice = isSimulated ? topo.setSelectedDevice : meraki.setSelectedDevice;
  const drillDown = isSimulated ? topo.drillDown : meraki.drillDown;
  const drillInto = isSimulated ? topo.drillInto : meraki.drillInto;
  const drillBack = isSimulated ? topo.drillBack : meraki.drillBack;
  const drillReset = isSimulated ? topo.drillReset : meraki.drillReset;

  const showSimStopped = isSimulated && !sim.isRunning;
  const showSimLoading = isSimulated && topo.isLoading && sim.isRunning;

  return (
    <div className="h-screen flex flex-col" style={{ background: 'var(--bg-primary)' }}>
      <TopBar
        dataSource={dataSource}
        onDataSourceChange={setDataSource}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        isConnected={topo.isConnected}
        pollCount={topo.pollCount}
        simulationRunning={sim.isRunning}
        simulationRemaining={sim.remainingSeconds}
        onSimulationStart={sim.start}
        onSimulationStop={sim.stop}
        merakiNetworks={meraki.networks}
        selectedNetwork={meraki.selectedNetwork}
        onNetworkChange={meraki.setSelectedNetwork}
        isRefreshing={meraki.isRefreshing}
        lastUpdated={meraki.lastUpdated}
        onRefresh={meraki.refresh}
      />
      <div className="flex-1 relative overflow-hidden">
        {showSimStopped ? (
          <div className="flex items-center justify-center h-full">
            <div style={{ fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-muted)', textAlign: 'center' }}>
              <div style={{ fontSize: '14px', marginBottom: '8px' }}>Simulation stopped.</div>
              <div style={{ fontSize: '11px' }}>Click Start Simulation to begin.</div>
            </div>
          </div>
        ) : showSimLoading ? (
          <div className="flex items-center justify-center h-full">
            <div style={{ fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-muted)' }}>SCANNING NETWORK...</div>
          </div>
        ) : viewMode === 'l2' ? (
          <ReactFlowProvider>
            <TopologyCanvas
              topology={l2}
              selectedDevice={selectedDevice}
              onSelectDevice={setSelectedDevice}
              drillDown={drillDown}
              onDrillInto={drillInto}
              onDrillBack={drillBack}
              onDrillReset={drillReset}
              deviceAnimations={isSimulated ? topo.deviceAnimations : undefined}
              pinnedDeviceIds={isSimulated ? topo.pinnedDeviceIds : undefined}
            />
          </ReactFlowProvider>
        ) : viewMode === 'hybrid' ? (
          <ReactFlowProvider>
            <HybridView l2Topology={l2} l3Topology={l3} onSelectDevice={setSelectedDevice} onSelectVlan={() => {}} />
          </ReactFlowProvider>
        ) : (
          <ReactFlowProvider>
            <L3View topology={l3} onSelectVlan={() => {}} />
          </ReactFlowProvider>
        )}

        {!isSimulated && meraki.isRefreshing && (
          <RefreshOverlay
            phase={meraki.refreshPhase}
            progress={meraki.refreshProgress}
            total={meraki.refreshTotal}
            remainingSeconds={meraki.remainingSeconds ?? 0}
          />
        )}

        {(viewMode === 'l2' || viewMode === 'hybrid') && isSimulated && (
          <DetailPanel device={selectedDevice} topology={l2} onClose={() => setSelectedDevice(null)} />
        )}
        {(viewMode === 'l2' || viewMode === 'hybrid') && !isSimulated && (
          <MerakiDetailPanel device={selectedDevice} topology={l2} clientCounts={meraki.clientCounts} onClose={() => setSelectedDevice(null)} />
        )}
      </div>
    </div>
  );
}

export default App;
