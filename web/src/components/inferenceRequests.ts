import type { InferenceParams } from '../api'

// Private browser recovery state, not a public DTO. No image bytes or filenames.
export type InferenceRequest = { params: InferenceParams; key: string; source_job_id?: string; job_id?: string }
const identifier = (v: unknown): v is string => typeof v === 'string' && v.length > 0 && v.length <= 160
export const validThreshold = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1
function valid(v: unknown): v is InferenceRequest {
  if (!v || typeof v !== 'object') return false
  const r = v as Partial<InferenceRequest>, p = r.params
  return Boolean(p && identifier(p.model_artifact_id) && identifier(p.image_artifact_id) && ['pt', 'onnx'].includes(p.backend) && validThreshold(p.confidence) && validThreshold(p.iou)
    && typeof r.key === 'string' && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(r.key)
    && (r.source_job_id === undefined || identifier(r.source_job_id)) && (r.job_id === undefined || identifier(r.job_id)))
}
export const sameInferenceParams = (a: InferenceParams, b: InferenceParams) => (['backend', 'model_artifact_id', 'image_artifact_id', 'confidence', 'iou'] as const).every(key => a[key] === b[key])

export function inferenceRequests(userId: string, projectId: string, warn: () => void) {
  // The server's idempotency namespace includes the authenticated actor. Never
  // adopt pre-v2 unscoped records after a logout/account switch.
  const prefix = `edgevision.inference.v2:${encodeURIComponent(userId)}:${encodeURIComponent(projectId)}:`, memory = new Map<string, InferenceRequest>()
  const identity = (p: InferenceParams, source?: string) => JSON.stringify([p.backend, p.model_artifact_id, p.image_artifact_id, p.confidence, p.iou, source ?? null])
  function read(key: string): InferenceRequest | null {
    try { const raw = sessionStorage.getItem(key); if (!raw) return null; const value: unknown = JSON.parse(raw); if (valid(value)) return value; warn() } catch { warn() }
    return null
  }
  function save(record: InferenceRequest, makeLast = false) {
    const key = prefix + identity(record.params, record.source_job_id), formKey = `${prefix}params:${identity(record.params)}`
    memory.set(key, record); memory.set(formKey, record)
    try {
      sessionStorage.setItem(key, JSON.stringify(record)); sessionStorage.setItem(formKey, JSON.stringify(record))
      if (makeLast) sessionStorage.setItem(`${prefix}last`, JSON.stringify(record))
    } catch { warn() }
  }
  return {
    last: () => { const last = read(`${prefix}last`); return last ? read(prefix + identity(last.params, last.source_job_id)) ?? last : null },
    forParams(params: InferenceParams) {
      const key = `${prefix}params:${identity(params)}`, saved = memory.get(key) ?? read(key)
      return saved && sameInferenceParams(saved.params, params) ? saved : null
    },
    get(params: InferenceParams, source?: string) {
      const key = prefix + identity(params, source), stored = memory.get(key) ?? read(key)
      const record = stored && identity(stored.params, stored.source_job_id) === identity(params, source) ? stored : { params: { ...params }, key: crypto.randomUUID(), ...(source ? { source_job_id: source } : {}) }
      save(record, true); return record
    }, save,
  }
}
