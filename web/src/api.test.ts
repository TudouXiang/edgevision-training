// @vitest-environment happy-dom
import { afterEach, expect, it, vi } from 'vitest'
import { ApiClientError, jobApi } from './api'
afterEach(() => { vi.unstubAllGlobals(); document.cookie = 'edgevision_csrf=; Max-Age=0; path=/' })
it('posts export through the authenticated job contract with a retained caller key and CSRF', async () => {
  document.cookie = 'edgevision_csrf=fixture-csrf; path=/'
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ job_id: 'export', state: 'queued' }), { status: 202 }))
  vi.stubGlobal('fetch', fetch)
  const signal = new AbortController().signal
  await jobApi.exportOnnx('project', { model_artifact_id: 'model', batch: 1, imgsz: 640, precision: 'fp32' }, 'same-key', signal)
  const [url, options] = fetch.mock.calls[0]
  expect(url).toBe('/api/v1/projects/project/jobs'); expect(options.method).toBe('POST'); expect(options.credentials).toBe('same-origin'); expect(options.signal).toBe(signal)
  expect(options.headers.get('Idempotency-Key')).toBe('same-key'); expect(options.headers.get('X-CSRF-Token')).toBe('fixture-csrf')
  expect(JSON.parse(options.body)).toEqual({ kind: 'export_onnx', params: { model_artifact_id: 'model', batch: 1, imgsz: 640, precision: 'fp32' } })
})
it('preserves the unavailable capability API error rather than inventing acceptance', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'EXPORT_UNAVAILABLE', message: '未验证' } }), { status: 503 })))
  await expect(jobApi.exportOnnx('p', { model_artifact_id: 'm', batch: 1, imgsz: 640, precision: 'fp32' }, 'key')).rejects.toMatchObject(new ApiClientError(503, 'EXPORT_UNAVAILABLE', '未验证'))
})
