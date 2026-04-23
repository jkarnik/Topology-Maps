// ui/src/hooks/useOrgDiff.ts
import { useState, useCallback } from 'react'
import { fetchOrgDiffRaw } from '../api/config'
import type { OrgDiffResponse } from '../types/config'

interface OrgDiffState {
  result: OrgDiffResponse | null
  loading: boolean
  error: string | null
  estimatedSeconds: number | null
  elapsed: number
}

export function useOrgDiff() {
  const [state, setState] = useState<OrgDiffState>({
    result: null,
    loading: false,
    error: null,
    estimatedSeconds: null,
    elapsed: 0,
  })

  const compare = useCallback(async (orgId: string, fromTs: string, toTs?: string) => {
    setState(s => ({ ...s, loading: true, error: null, result: null, elapsed: 0, estimatedSeconds: null }))
    const startedAt = Date.now()

    // Tick elapsed every second while loading
    const ticker = setInterval(() => {
      setState(s => s.loading ? { ...s, elapsed: Math.floor((Date.now() - startedAt) / 1000) } : s)
    }, 1000)

    try {
      // Use fetchOrgDiffRaw to avoid URL duplication; we need raw Response for headers
      const resp = await fetchOrgDiffRaw(orgId, fromTs, toTs)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const estimated = parseInt(resp.headers.get('X-Estimated-Seconds') ?? '0', 10) || null
      setState(s => ({ ...s, estimatedSeconds: estimated }))
      const data: OrgDiffResponse = await resp.json()
      setState(s => ({ ...s, result: data, loading: false }))
    } catch (e) {
      setState(s => ({ ...s, loading: false, error: String(e) }))
    } finally {
      clearInterval(ticker)
    }
  }, [])

  const clear = useCallback(() => {
    setState({ result: null, loading: false, error: null, estimatedSeconds: null, elapsed: 0 })
  }, [])

  return { ...state, compare, clear }
}
