import { useState, useEffect } from 'react'
import { getCoverage } from '../api/compare'
import type { CoverageResponse } from '../types/config'

export function useCoverage(orgId: string | null) {
  const [data, setData] = useState<CoverageResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!orgId) return
    setLoading(true)
    setError(null)
    getCoverage(orgId)
      .then(d => { setData(d); setLoading(false); setError(null) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [orgId])

  return { data, loading, error }
}
