import type {
  NetworkCompareResponse,
  CoverageResponse,
  ConfigTemplate,
  TemplateScoresResponse,
} from '../types/config'

const BASE = '/api/config'

async function _fetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${path}`)
  return res.json()
}

export function compareNetworks(
  orgId: string,
  networkA: string,
  networkB: string,
): Promise<NetworkCompareResponse> {
  const qs = new URLSearchParams({ org_id: orgId, network_a: networkA, network_b: networkB })
  return _fetch(`/compare/networks?${qs}`)
}

export function getCoverage(orgId: string): Promise<CoverageResponse> {
  return _fetch(`/coverage?${new URLSearchParams({ org_id: orgId })}`)
}

export function listTemplates(orgId: string): Promise<ConfigTemplate[]> {
  return _fetch(`/templates?${new URLSearchParams({ org_id: orgId })}`)
}

export function createTemplate(orgId: string, name: string, networkId: string): Promise<ConfigTemplate> {
  return _fetch('/templates', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ org_id: orgId, name, network_id: networkId }),
  })
}

export function deleteTemplate(templateId: number): Promise<{ deleted: number }> {
  return _fetch(`/templates/${templateId}`, { method: 'DELETE' })
}

export function getTemplateScores(templateId: number, orgId: string): Promise<TemplateScoresResponse> {
  return _fetch(`/templates/${templateId}/scores?${new URLSearchParams({ org_id: orgId })}`)
}
