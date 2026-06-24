// New Relic Browser agent (real-user monitoring) for the Topology Maps UI.
// Config values come from the "topology-maps-ui" browser app in New Relic
// (account 7980758). Imported first in main.tsx so the agent initializes
// before the React app renders.
import { BrowserAgent } from '@newrelic/browser-agent/loaders/browser-agent'

new BrowserAgent({
  init: {
    distributed_tracing: { enabled: true },
    privacy: { cookies_enabled: true },
    ajax: { deny_list: ['bam.nr-data.net'] },
  },
  info: {
    beacon: 'bam.nr-data.net',
    errorBeacon: 'bam.nr-data.net',
    licenseKey: 'NRJS-a00384a979c142692bc',
    applicationID: '653425513',
    sa: 1,
  },
  loader_config: {
    accountID: '7980758',
    trustKey: '7980758',
    agentID: '653425513',
    applicationID: '653425513',
    licenseKey: 'NRJS-a00384a979c142692bc',
  },
})
