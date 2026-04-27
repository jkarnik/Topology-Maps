import { useState, useCallback } from 'react'
import { compareNetworks } from '../api/compare'
import type { NetworkCompareResponse } from '../types/config'

interface State {
  result: NetworkCompareResponse | null
  loading: boolean
  error: string | null
}

export function useNetworkCompare() {
  const [state, setState] = useState<State>({ result: null, loading: false, error: null })

  const compare = useCallback(async (orgId: string, networkA: string, networkB: string) => {
    setState({ result: null, loading: true, error: null })
    try {
      const data = await compareNetworks(orgId, networkA, networkB)
      setState({ result: data, loading: false, error: null })
    } catch (e) {
      setState({ result: null, loading: false, error: String(e) })
    }
  }, [])

  const clear = useCallback(() => setState({ result: null, loading: false, error: null }), [])

  return { ...state, compare, clear }
}
