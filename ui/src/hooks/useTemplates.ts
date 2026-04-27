import { useState, useEffect, useCallback } from 'react'
import { listTemplates, createTemplate, deleteTemplate } from '../api/compare'
import type { ConfigTemplate } from '../types/config'

export function useTemplates(orgId: string | null) {
  const [templates, setTemplates] = useState<ConfigTemplate[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(() => {
    if (!orgId) return
    setLoading(true)
    listTemplates(orgId)
      .then(t => { setTemplates(t); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [orgId])

  useEffect(() => { reload() }, [reload])

  const promote = useCallback(async (name: string, networkId: string) => {
    if (!orgId) return
    await createTemplate(orgId, name, networkId)
    reload()
  }, [orgId, reload])

  const remove = useCallback(async (templateId: number) => {
    await deleteTemplate(templateId)
    reload()
  }, [reload])

  return { templates, loading, error, promote, remove, reload }
}
