import { useState, useEffect } from 'react'
import { getTemplateScores } from '../api/compare'
import type { TemplateScoresResponse, DeviceTemplateScoresResponse } from '../types/config'

export type AnyScoresResponse = TemplateScoresResponse | DeviceTemplateScoresResponse

export function isSiteScores(r: AnyScoresResponse): r is TemplateScoresResponse {
  return 'scores' in r
}

export function useTemplateScores(templateId: number | null, orgId: string | null) {
  const [data, setData] = useState<AnyScoresResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!templateId || !orgId) { setData(null); return }
    setLoading(true)
    setError(null)
    getTemplateScores(templateId, orgId)
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [templateId, orgId])

  return { data, loading, error }
}
