import type { components } from '../../contracts/generated/openapi'

type LiveResponse = components['schemas']['LiveResponse']
type ReadyResponse = components['schemas']['ReadyResponse']
export type Capabilities = components['schemas']['CapabilitiesResponse']
export type User = components['schemas']['UserPublic']
export type Project = components['schemas']['ProjectPublic']
export type Dataset = components['schemas']['DatasetPublic']
export type Job = components['schemas']['JobPublic']
export type JobLog = components['schemas']['JobLog']
export type Metric = components['schemas']['Metric']
export type Artifact = components['schemas']['ArtifactPublic']
export type TrainParams = components['schemas']['TrainParams']
export type JobAccepted = components['schemas']['JobAccepted']
type JobPage = components['schemas']['Page_JobPublic_']
type JobLogs = components['schemas']['Incremental_JobLog_']
export type DatasetSample = components['schemas']['DatasetSamplePublic']
type ProjectPage = components['schemas']['Page_ProjectPublic_']
type DatasetPage = components['schemas']['Page_DatasetPublic_']
type DatasetSamplePage = components['schemas']['Page_DatasetSamplePublic_']
type UserPage = components['schemas']['Page_UserPublic_']
type LoginBody = components['schemas']['LoginRequest']
type ProjectCreateBody = components['schemas']['ProjectCreate']
type ProjectUpdateBody = components['schemas']['ProjectUpdate']
type UserCreateBody = components['schemas']['UserCreate']

interface ErrorEnvelope { error?: { code?: string; message?: string } }

export class ApiClientError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message) }
}

function cookie(name: string): string | null {
  const prefix = `${name}=`
  const item = document.cookie.split(';').map(value => value.trim()).find(value => value.startsWith(prefix))
  return item ? decodeURIComponent(item.slice(prefix.length)) : null
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase()
  const headers = new Headers(options.headers)
  if (options.body !== undefined && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && path !== '/auth/login') {
    const csrf = cookie('edgevision_csrf')
    if (csrf) headers.set('X-CSRF-Token', csrf)
  }
  const response = await fetch(`/api/v1${path}`, { ...options, method, headers, credentials: 'same-origin' })
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as ErrorEnvelope
    throw new ApiClientError(response.status, body.error?.code ?? 'HTTP_ERROR', body.error?.message ?? `HTTP ${response.status}`)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function checkSystem(signal: AbortSignal): Promise<{ live: LiveResponse; ready: ReadyResponse | null; capabilities: Capabilities | null }> {
  const live = await request<LiveResponse>('/health/live', { signal })
  const [ready, capabilities] = await Promise.all([
    request<ReadyResponse>('/health/ready', { signal }).catch(() => null),
    request<Capabilities>('/capabilities', { signal }).catch(() => null),
  ])
  return { live, ready, capabilities }
}

export const authApi = {
  me: (signal?: AbortSignal) => request<User>('/auth/me', { signal }),
  login: (body: LoginBody, signal?: AbortSignal) => request<User>('/auth/login', { method: 'POST', body: JSON.stringify(body), signal }),
  logout: (signal?: AbortSignal) => request<void>('/auth/logout', { method: 'POST', signal }),
  changePassword: (current_password: string, new_password: string, signal?: AbortSignal) => request<void>('/auth/change-password', {
    method: 'POST', body: JSON.stringify({ current_password, new_password }), signal,
  }),
}

export const projectApi = {
  list: (page = 1, pageSize = 20, signal?: AbortSignal) => request<ProjectPage>(`/projects?page=${page}&page_size=${pageSize}`, { signal }),
  create: (body: ProjectCreateBody, signal?: AbortSignal) => request<Project>('/projects', { method: 'POST', body: JSON.stringify(body), signal }),
  update: (id: string, body: ProjectUpdateBody, signal?: AbortSignal) => request<Project>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(body), signal }),
  archive: (id: string, signal?: AbortSignal) => request<Project>(`/projects/${id}/archive`, { method: 'POST', signal }),
}

export const jobApi = {
  train: (projectId: string, params: TrainParams, key: string, signal?: AbortSignal, source_job_id?: string) => request<JobAccepted>(`/projects/${projectId}/jobs`, { method: 'POST', body: JSON.stringify({kind: 'train', params, source_job_id}), headers: {'Idempotency-Key': key}, signal }),
  metrics: (id: string, cursor: string | null, signal?: AbortSignal) => request<components['schemas']['Incremental_Metric_']>(`/jobs/${id}/metrics?limit=500${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`, { signal }),
  artifacts: (projectId: string, signal?: AbortSignal, page = 1) => request<components['schemas']['Page_ArtifactPublic_']>(`/projects/${projectId}/artifacts?page=${page}&page_size=100`, { signal }),
  list: (projectId: string, signal?: AbortSignal, page = 1) => request<JobPage>(`/projects/${projectId}/jobs?page=${page}&page_size=20`, { signal }),
  detail: (id: string, signal?: AbortSignal) => request<Job>(`/jobs/${id}`, { signal }),
  cancel: (id: string, signal?: AbortSignal) => request<Job>(`/jobs/${id}/cancel`, { method: 'POST', signal }),
  logs: (id: string, cursor: string | null, signal?: AbortSignal) => request<JobLogs>(`/jobs/${id}/logs?limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`, { signal }),
}

export const datasetApi = {
  detail: (id: string, signal?: AbortSignal) => request<Dataset>(`/datasets/${id}`, { signal }),
  check: (id: string, key: string, signal?: AbortSignal) => request<JobAccepted>(`/datasets/${id}/check`, { method: 'POST', headers: { 'Idempotency-Key': key }, signal }),
  list: (projectId: string, page = 1, pageSize = 20, signal?: AbortSignal) => request<DatasetPage>(`/projects/${projectId}/datasets?page=${page}&page_size=${pageSize}`, { signal }),
  upload: (projectId: string, file: File, signal?: AbortSignal) => {
    const body = new FormData()
    body.append('file', file, file.name)
    return request<Dataset>(`/projects/${projectId}/datasets`, { method: 'POST', body, signal })
  },
  samples: (datasetId: string, page = 1, pageSize = 12, signal?: AbortSignal) => request<DatasetSamplePage>(`/datasets/${datasetId}/samples?page=${page}&page_size=${pageSize}`, { signal }),
}

export const adminApi = {
  users: (page = 1, pageSize = 20, signal?: AbortSignal) => request<UserPage>(`/admin/users?page=${page}&page_size=${pageSize}`, { signal }),
  createUser: (body: UserCreateBody, signal?: AbortSignal) => request<User>('/admin/users', { method: 'POST', body: JSON.stringify(body), signal }),
  setUserActive: (id: string, is_active: boolean, signal?: AbortSignal) => request<User>(`/admin/users/${id}`, {
    method: 'PATCH', body: JSON.stringify({ is_active }), signal,
  }),
}
