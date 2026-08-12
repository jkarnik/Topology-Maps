import { useState, useEffect } from 'react';
import { ReactFlowProvider } from '@xyflow/react';
import { useTopology } from './hooks/useTopology';
import { useSimulation } from './hooks/useSimulation';
import { useMerakiTopology } from './hooks/useMerakiTopology';
import { useMerakiSites } from './hooks/useMerakiSites';
import TopBar from './components/TopBar';
import TopologyCanvas from './components/TopologyCanvas';
import DetailPanel from './components/DetailPanel';
import MerakiDetailPanel from './components/MerakiDetailPanel';
import RefreshOverlay from './components/RefreshOverlay';
import L3View from './components/L3View';
import HybridView from './components/HybridView';
import WorldMapView from './components/WorldMapView';
import { ConfigBrowser } from './components/ConfigBrowser';
import type { DataSource } from './types/topology';

function App() {
  const [dataSource, setDataSource] = useState<DataSource>('meraki');
  const sim = useSimulation();
  const topo = useTopology();
  const meraki = useMerakiTopology();
  const merakiSites = useMerakiSites();

  // World-map landing state — 'map' is the default for Meraki; clicking a
  // site (or the network-jump dropdown) moves to 'site'.
  const [merakiView, setMerakiView] = useState<'map' | 'site'>('map');
  const [transitionOrigin, setTransitionOrigin] = useState<{ xPct: number; yPct: number }>({
    xPct: 50,
    yPct: 50,
  });
  const [isTransitioning, setIsTransitioning] = useState(false);

  // First-switch trigger for Meraki. The world map is the landing view, so
  // this now only needs the lightweight sites summary — not a specific
  // network's full L2/L3 topology. Resolution order for sites mirrors the
  // topology cache: localStorage (synchronous, inside useMerakiSites) →
  // server-side snapshot → live Meraki API. The network-jump dropdown
  // still needs `meraki.networks`, so that's fetched too, but without the
  // eager `refresh(networkId)` call the old effect used to make.
  const [merakiInitialized, setMerakiInitialized] = useState(false);
  useEffect(() => {
    if (dataSource !== 'meraki' || merakiInitialized) return;
    setMerakiInitialized(true);

    if (meraki.networks.length === 0) {
      // Seed file first: it's the only path that hydrates isConfigured /
      // cacheRef / networks from the server-side snapshot without hitting the
      // live Meraki API. Fall back to the live networks list if it misses.
      meraki.loadSeedFile().then((seedOk) => {
        if (!seedOk) meraki.fetchNetworks();
      });
    }
    merakiSites.loadCached().then((hit) => {
      if (!hit) merakiSites.refresh();
    });
  }, [dataSource, merakiInitialized]);

  // The TopBar network dropdown is a shortcut straight to a site's topology,
  // so picking one has to leave the world map too.
  const handleNetworkChange = (id: string | null) => {
    meraki.setSelectedNetwork(id);
    if (id) setMerakiView('site');
  };

  // Opening Meraki always lands on the world map, so leaving Meraki resets the
  // drilled-in site view.
  const handleDataSourceChange = (next: DataSource) => {
    if (dataSource === 'meraki' && next !== 'meraki') {
      setMerakiView('map');
    }
    setDataSource(next);
  };

  const handleSelectSite = (networkId: string, origin: { xPct: number; yPct: number }) => {
    setTransitionOrigin(origin);
    setIsTransitioning(true);
    meraki.setSelectedNetwork(networkId);
    window.setTimeout(() => {
      setMerakiView('site');
      setIsTransitioning(false);
    }, 400);
  };

  const handleBackToMap = () => {
    setIsTransitioning(true);
    window.setTimeout(() => {
      setMerakiView('map');
      setIsTransitioning(false);
    }, 300);
  };

  const isSimulated = dataSource === 'simulated';
  const showWorldMap = dataSource === 'meraki' && merakiView === 'map';
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
        onDataSourceChange={handleDataSourceChange}
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
        onNetworkChange={handleNetworkChange}
        isRefreshing={showWorldMap ? merakiSites.isLoading : meraki.isRefreshing}
        lastUpdated={showWorldMap ? merakiSites.lastUpdated : meraki.lastUpdated}
        onRefresh={showWorldMap ? merakiSites.refresh : meraki.refresh}
        onSaveSnapshot={meraki.saveSnapshot}
        merakiView={merakiView}
        onBackToMap={handleBackToMap}
      />
      <div className="flex-1 relative overflow-hidden">
        {dataSource === 'configs' ? (
          <ConfigBrowser />
        ) : showWorldMap ? (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'var(--bg-primary)',
              transformOrigin: `${transitionOrigin.xPct}% ${transitionOrigin.yPct}%`,
              transform: isTransitioning ? 'scale(2.4)' : 'scale(1)',
              opacity: isTransitioning ? 0 : 1,
              transition: 'transform 0.4s ease, opacity 0.4s ease',
            }}
          >
            <WorldMapView
              sites={merakiSites.sites}
              isConfigured={meraki.isConfigured}
              isLoading={merakiSites.isLoading}
              error={merakiSites.error}
              onSelectSite={handleSelectSite}
            />
          </div>
        ) : (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              opacity: isTransitioning ? 0 : 1,
              transition: 'opacity 0.3s ease',
            }}
          >
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
                <HybridView l2Topology={l2} l3Topology={l3} onSelectDevice={setSelectedDevice} onSelectVlan={() => {}} gatewayLabel={isSimulated ? 'FortiGate' : 'Meraki Gateway'} />
              </ReactFlowProvider>
            ) : (
              <ReactFlowProvider>
                <L3View topology={l3} onSelectVlan={() => {}} gatewayLabel={isSimulated ? 'FortiGate' : 'Meraki Gateway'} />
              </ReactFlowProvider>
            )}
          </div>
        )}

        {!showWorldMap && !isSimulated && meraki.isRefreshing && (
          <RefreshOverlay
            phase={meraki.refreshPhase}
            progress={meraki.refreshProgress}
            total={meraki.refreshTotal}
            message={meraki.loadingMessage}
          />
        )}

        {!showWorldMap && (viewMode === 'l2' || viewMode === 'hybrid') && isSimulated && (
          <DetailPanel device={selectedDevice} topology={l2} onClose={() => setSelectedDevice(null)} />
        )}
        {!showWorldMap && (viewMode === 'l2' || viewMode === 'hybrid') && !isSimulated && (
          <MerakiDetailPanel
            device={selectedDevice}
            topology={l2}
            clientCounts={meraki.clientCounts}
            onClose={() => setSelectedDevice(null)}
            onGetDeviceDetail={meraki.getDeviceDetail}
          />
        )}
      </div>
    </div>
  );
}

export default App;
