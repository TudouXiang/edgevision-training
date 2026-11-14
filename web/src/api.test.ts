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

it('submits infer through the generated job contract with retry origin and retained key', async () => {
  document.cookie = 'edgevision_csrf=fixture-csrf; path=/'
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ job_id: 'infer', state: 'queued' }), { status: 202 })); vi.stubGlobal('fetch', fetch)
  const signal = new AbortController().signal, params = { model_artifact_id: 'onnx', image_artifact_id: 'image', backend: 'onnx' as const, confidence: .25, iou: .45 }
  await jobApi.infer('project', params, 'saved-key', signal, 'failed-job')
  const [url, options] = fetch.mock.calls[0]; expect(url).toBe('/api/v1/projects/project/jobs'); expect(options.credentials).toBe('same-origin'); expect(options.signal).toBe(signal)
  expect(options.headers.get('Idempotency-Key')).toBe('saved-key'); expect(options.headers.get('X-CSRF-Token')).toBe('fixture-csrf'); expect(JSON.parse(options.body)).toEqual({ kind: 'infer', params, source_job_id: 'failed-job' })
})
it('uploads exactly one file and reads result and authenticated preview by result artifact ID', async () => {
  const { inferenceApi } = await import('./api')
  document.cookie = 'edgevision_csrf=fixture-csrf; path=/'
  const fetch = vi.fn().mockResolvedValueOnce(new Response('{}', { status: 201 })).mockResolvedValueOnce(new Response('{}')).mockResolvedValueOnce(new Response('png-mock', { headers: { 'Content-Type': 'image/png' } })); vi.stubGlobal('fetch', fetch)
  const file = new File(['synthetic'], 'input.png', { type: 'image/png' }), signal = new AbortController().signal
  await inferenceApi.upload('project', file, signal); await inferenceApi.result('result-artifact', signal); await inferenceApi.preview('result-artifact', signal)
  const [url, options] = fetch.mock.calls[0]; expect(url).toBe('/api/v1/projects/project/images'); expect(options.headers.has('Content-Type')).toBe(false); expect(options.headers.get('X-CSRF-Token')).toBe('fixture-csrf')
  expect([...options.body.keys()]).toEqual(['file']); expect(options.body.get('file').name).toBe('input.png'); expect(options.headers.has('Idempotency-Key')).toBe(false)
  expect(fetch.mock.calls.map(c => c[0]).slice(1)).toEqual(['/api/v1/inferences/result-artifact', '/api/v1/inferences/result-artifact/image'])
  expect(fetch.mock.calls[2][1]).toMatchObject({ credentials: 'same-origin', signal })
})
it('preserves preview authentication errors and rejects unexpected content types', async () => {
  const { inferenceApi } = await import('./api')
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ error: { code: 'SESSION_EXPIRED', message: '会话失效' } }), { status: 401 })).mockResolvedValueOnce(new Response('html', { headers: { 'Content-Type': 'text/html' } })))
  await expect(inferenceApi.preview('result')).rejects.toMatchObject({ status: 401, code: 'SESSION_EXPIRED' }); await expect(inferenceApi.preview('result')).rejects.toThrow('Unexpected preview format')
})

it('reads bounded administrator task pages with same-origin session and cancellation signal',async()=>{
 const {adminApi}=await import('./api')
 const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({items:[],total:0,page:2,page_size:20})))
 vi.stubGlobal('fetch',fetch); const signal=new AbortController().signal
 await adminApi.jobs(2,20,signal)
 expect(fetch.mock.calls[0][0]).toBe('/api/v1/admin/jobs?page=2&page_size=20')
 expect(fetch.mock.calls[0][1]).toMatchObject({credentials:'same-origin',signal})
})
