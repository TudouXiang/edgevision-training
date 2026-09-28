import type { components } from '../../contracts/generated/openapi'

type LiveResponse = components['schemas']['LiveResponse']
type ReadyResponse = components['schemas']['ReadyResponse']
export type Capabilities = components['schemas']['CapabilitiesResponse']

async function get<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`/api/v1${path}`, { credentials: 'same-origin', signal })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json() as Promise<T>
}

export async function checkSystem(signal: AbortSignal): Promise<{
  live: LiveResponse
  ready: ReadyResponse | null
  capabilities: Capabilities | null
}> {
  const live = await get<LiveResponse>('/health/live', signal)
  const [ready, capabilities] = await Promise.all([
    get<ReadyResponse>('/health/ready', signal).catch(() => null),
    get<Capabilities>('/capabilities', signal).catch(() => null),
  ])
  return { live, ready, capabilities }
}
