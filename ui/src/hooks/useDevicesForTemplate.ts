import { useState, useEffect } from 'react'
import { listDevicesForTemplate } from '../api/compare'
import type { TemplateKind } from '../types/config'

export interface DeviceOption {
  serial: string
  name: string | null
}

export function useDevicesForTemplate(
  orgId: string | null,
  networkId: string | null,
  kind: TemplateKind | null,
) {
  const [devices, setDevices] = useState<DeviceOption[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!orgId || !networkId || !kind || kind === 'site') {
      setDevices([])
      return
    }
    setLoading(true)
    setError(null)
    listDevicesForTemplate(orgId, networkId, kind)
      .then(r => { setDevices(r.devices); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [orgId, networkId, kind])

  return { devices, loading, error }
}
