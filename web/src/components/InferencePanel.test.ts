// @vitest-environment happy-dom
// Explicit synthetic API mocks. These tests do not execute PT/ORT or establish business acceptance.
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import InferencePanel from './InferencePanel.vue'
import { ApiClientError, inferenceApi, jobApi } from '../api'
import type { Artifact, InferenceInput, Job, JobAccepted } from '../api'
import { capability, date, imageInput, inferJob, inferParams, inferenceResult, onnx, output, project, pt, sourceJob } from './InferencePanel.fixtures'
import { inferenceRequests } from './inferenceRequests'

const page = <T,>(items: T[]) => ({ items, total: items.length, page: 1, page_size: 100 })
function deferred<T>() { let resolve!: (v: T) => void, reject!: (e: unknown) => void; const promise = new Promise<T>((ok, no) => { resolve = ok; reject = no }); return { promise, resolve, reject } }
const wrappers: ReturnType<typeof mount>[] = []
function create(extra = {}) { const wrapper = mount(InferencePanel, { props: { userId: 'u', project, ptCapability: capability, onnxCapability: capability, ...extra } }); wrappers.push(wrapper); return wrapper }
function button(wrapper: ReturnType<typeof mount>, text: string) { return wrapper.findAll('button').find(item => item.text() === text)! }
async function form(wrapper: ReturnType<typeof mount>) { await wrapper.findAll('.inference-form select')[1].setValue('onnx-a'); await wrapper.findAll('.inference-form select')[2].setValue('image-a'); await flushPromises() }
async function selectFile(wrapper: ReturnType<typeof mount>, name = 'test.png', type = 'image/png', content = 'synthetic') {
  const file = new File([content], name, { type }); Object.defineProperty(wrapper.find('input[type=file]').element, 'files', { configurable: true, value: [file] })
  await wrapper.find('input[type=file]').trigger('change'); await flushPromises(); return file
}
function mocks() {
  vi.useFakeTimers()
  vi.spyOn(jobApi, 'list').mockResolvedValue(page([inferJob()]))
  vi.spyOn(jobApi, 'detail').mockImplementation(async id => id.startsWith('train') ? sourceJob(id, 'succeeded', 'p', 'train') : id.startsWith('export') ? sourceJob(id, 'succeeded') : inferJob(id))
  vi.spyOn(jobApi, 'artifacts').mockResolvedValue(page<Artifact>([pt(), onnx(), { ...onnx(), id: 'onnx-b' }, imageInput()]))
  vi.spyOn(jobApi, 'logs').mockResolvedValue({ items: [], next_cursor: null, eof: false, job_state: 'running' })
  vi.spyOn(jobApi, 'infer').mockResolvedValue({ job_id: 'infer-new', state: 'queued' })
  vi.spyOn(jobApi, 'cancel').mockImplementation(async id => inferJob(id, 'cancelled'))
  vi.spyOn(inferenceApi, 'upload').mockResolvedValue(imageInput('image-new'))
  vi.spyOn(inferenceApi, 'result').mockResolvedValue(inferenceResult())
  vi.spyOn(inferenceApi, 'preview').mockResolvedValue(new Blob(['synthetic'], { type: 'image/png' }))
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:synthetic-preview')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
}
function succeeded() {
  vi.mocked(jobApi.detail).mockImplementation(async id => id.startsWith('train') ? sourceJob(id, 'succeeded', 'p', 'train') : id.startsWith('export') ? sourceJob(id, 'succeeded') : inferJob(id, 'succeeded'))
  vi.mocked(jobApi.artifacts).mockResolvedValue(page<Artifact>([pt(), onnx(), imageInput(), output()]))
  vi.mocked(jobApi.logs).mockResolvedValue({ items: [], next_cursor: null, eof: true, job_state: 'succeeded' })
}
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); sessionStorage.clear() })

it('binds the chosen backend to same-project passed models with successful source jobs', async () => {
  mocks()
  vi.mocked(jobApi.artifacts).mockResolvedValue(page<Artifact>([pt(), onnx(), { ...onnx(), id: 'foreign', project_id: 'foreign' }, ({ ...onnx(), id: 'bad', validation_state: 'failed' } as unknown as Artifact), { ...onnx(), id: 'failed-source', job_id: 'failed' }, imageInput(), imageInput('foreign-image', 'foreign')]))
  vi.mocked(jobApi.detail).mockImplementation(async id => id === 'failed' ? sourceJob(id, 'failed') : id.startsWith('train') ? sourceJob(id, 'succeeded', 'p', 'train') : id.startsWith('export') ? sourceJob(id, 'succeeded') : inferJob(id))
  const w = create(); await flushPromises()
  expect(w.findAll('.inference-form select')[1].findAll('option').map(o => o.attributes('value'))).toEqual(['', 'onnx-a'])
  expect(w.findAll('.inference-form select')[2].findAll('option')).toHaveLength(2)
  await w.findAll('.inference-form select')[0].setValue('pt'); await flushPromises()
  expect(w.findAll('.inference-form select')[1].findAll('option').map(o => o.attributes('value'))).toEqual(['', 'pt-a'])
  await w.findAll('.inference-form select')[1].setValue('pt-a'); await w.findAll('.inference-form select')[2].setValue('image-a'); await w.find('.inference-form').trigger('submit'); await flushPromises()
  expect(vi.mocked(jobApi.infer).mock.calls[0][1]).toEqual({ ...inferParams, backend: 'pt', model_artifact_id: 'pt-a' })
})
it('shows only a verified result artifact and uses EXIF-corrected original coordinates, not encoded or preview dimensions', async () => {
  mocks(); succeeded(); const w = create(); await flushPromises()
  expect(inferenceApi.result).toHaveBeenCalledWith('result-a', expect.any(AbortSignal)); expect(inferenceApi.preview).toHaveBeenCalledWith('result-a', expect.any(AbortSignal))
  expect(w.find('svg').attributes('viewBox')).toBe('0 0 2400 1600'); expect(w.find('image').attributes('width')).toBe('2400'); expect(w.find('image').attributes('height')).toBe('1600')
  expect(w.find('rect').attributes()).toMatchObject({ x: '120', y: '240', width: '880', height: '960' })
  expect(w.text()).toContain('CPUExecutionProvider'); expect(w.text()).toContain('1280 × 853'); expect(w.text()).toContain('score 0.87654')
  expect(w.findAll('a')).toHaveLength(1); expect(w.find('a').attributes('href')).toBe('/api/v1/artifacts/result-a/download')
  expect(w.find('image').attributes('href')).toBe('blob:synthetic-preview')
})
it('accepts a real-contract empty result without inventing boxes', async () => {
  mocks(); succeeded(); vi.mocked(inferenceApi.result).mockResolvedValue(inferenceResult(true)); const w = create(); await flushPromises()
  expect(w.text()).toContain('合法的空检测成功结果'); expect(w.findAll('rect')).toHaveLength(0); expect(w.find('a').exists()).toBe(true)
})
it.each(['capability', 'archive', 'threshold'])('blocks new submissions for %s without fake acceptance', async mode => {
  mocks(); const w = create(mode === 'capability' ? { onnxCapability: { ...capability, available: false, reason: '未通过当前环境探针' } } : mode === 'archive' ? { project: { ...project, archived_at: date } } : {}); await flushPromises(); await form(w)
  if (mode === 'threshold') await w.findAll('.inference-form input')[0].setValue('1.01')
  await w.find('.inference-form').trigger('submit'); expect(jobApi.infer).not.toHaveBeenCalled(); expect(w.find('.inference-form button').attributes('disabled')).toBeDefined()
  if (mode === 'capability') expect(w.text()).toContain('未通过当前环境探针')
})
it.each(['-0.1', '', 'Infinity'])('rejects invalid IoU %s', async value => {
  mocks(); const w = create(); await flushPromises(); await form(w); await w.findAll('.inference-form input')[1].setValue(value); await w.find('.inference-form').trigger('submit'); expect(jobApi.infer).not.toHaveBeenCalled()
})
it.each([['example.jpeg', 'image/jpeg'], ['example.png', 'image/png']])('uploads %s once and labels bytes unverified without preview/download', async (name, type) => {
  mocks(); const pending = deferred<InferenceInput>(); vi.mocked(inferenceApi.upload).mockReturnValue(pending.promise)
  const w = create(); await flushPromises(); const file = await selectFile(w, name, type)
  await w.find('.inference-upload').trigger('submit'); await w.find('.inference-upload').trigger('submit'); expect(inferenceApi.upload).toHaveBeenCalledTimes(1)
  expect(vi.mocked(inferenceApi.upload).mock.calls[0].slice(0, 2)).toEqual(['p', file])
  vi.mocked(jobApi.artifacts).mockResolvedValue(page<Artifact>([pt(), onnx(), imageInput('image-new')]))
  pending.resolve(imageInput('image-new')); await flushPromises()
  expect((w.findAll('.inference-form select')[2].element as HTMLSelectElement).value).toBe('image-new'); expect(w.text()).toContain('unverified'); expect(w.find('image').exists()).toBe(false); expect(w.find('a').exists()).toBe(false)
})
it.each([['bad.gif', 'image/gif', 'gif'], ['empty.png', 'image/png', '']])('rejects locally invalid upload %s', async (name, type, content) => {
  mocks(); const w = create(); await flushPromises(); await selectFile(w, name, type, content); await w.find('.inference-upload').trigger('submit'); expect(inferenceApi.upload).not.toHaveBeenCalled(); expect(w.text()).toContain('请选择非空 JPEG/PNG')
})
it.each(['model', 'project', 'unmount'])('discards late upload after %s changes and aborts the old request', async mode => {
  mocks(); const pending = deferred<InferenceInput>(); vi.mocked(inferenceApi.upload).mockReturnValue(pending.promise)
  const w = create(); await flushPromises(); await selectFile(w); await w.find('.inference-upload').trigger('submit'); const signal = vi.mocked(inferenceApi.upload).mock.calls[0][2]!
  if (mode === 'model') await w.findAll('.inference-form select')[1].setValue('onnx-b')
  else if (mode === 'project') await w.setProps({ project: { ...project, id: 'p-new' } })
  else w.unmount()
  pending.resolve(imageInput('late-input')); await flushPromises(); expect(signal.aborted).toBe(true)
  if (mode !== 'unmount') { expect(w.text()).not.toContain('late-input'); if (mode === 'model') expect((w.findAll('.inference-form select')[1].element as HTMLSelectElement).value).toBe('onnx-b') }
})
it('deduplicates repeated submit and retains the accepted job even if its detail read fails', async () => {
  mocks(); const pending = deferred<JobAccepted>(); vi.mocked(jobApi.infer).mockReturnValue(pending.promise)
  const detail = vi.mocked(jobApi.detail).getMockImplementation()!; vi.mocked(jobApi.detail).mockImplementation((id, signal) => id === 'accepted-only' ? Promise.reject(new Error('offline')) : detail(id, signal))
  const w = create(); await flushPromises(); await form(w); await w.find('.inference-form').trigger('submit'); await w.find('.inference-form').trigger('submit'); expect(jobApi.infer).toHaveBeenCalledTimes(1)
  pending.resolve({ job_id: 'accepted-only', state: 'queued' }); await flushPromises(); await w.find('.inference-form').trigger('submit'); await flushPromises()
  expect(jobApi.infer).toHaveBeenCalledTimes(1); expect(w.text()).toContain('已接收任务 accepted-only'); w.unmount()
  const reloaded = create(); await flushPromises(); expect(reloaded.text()).toContain('已接收任务 accepted-only'); expect(jobApi.detail).toHaveBeenCalledWith('accepted-only', expect.any(AbortSignal)); expect(jobApi.infer).toHaveBeenCalledTimes(1)
  vi.mocked(jobApi.detail).mockImplementation(async (id, signal) => id === 'accepted-only' ? inferJob(id, 'running') : detail(id, signal)); await vi.advanceTimersByTimeAsync(4000); await flushPromises(); expect(reloaded.find('.identity').text()).toBe('accepted-only')
})
it('recovers a lost POST response across remount with identical params and idempotency key', async () => {
  mocks(); vi.mocked(jobApi.infer).mockRejectedValueOnce(new Error('lost response'))
  const first = create(); await flushPromises(); await form(first); await first.find('.inference-form').trigger('submit'); await flushPromises(); first.unmount()
  const second = create(); await flushPromises(); expect(second.text()).toContain('已保留提交参数和幂等标识'); await second.find('.inference-form').trigger('submit'); await flushPromises()
  const calls = vi.mocked(jobApi.infer).mock.calls; expect(calls).toHaveLength(2); expect(calls[0][2]).toBe(calls[1][2]); expect(calls[0][1]).toEqual(calls[1][1])
})
it.each(['model', 'project', 'unmount'])('does not let a late submission overwrite a newer %s', async mode => {
  mocks(); const pending = deferred<JobAccepted>(); vi.mocked(jobApi.infer).mockReturnValue(pending.promise)
  const w = create(); await flushPromises(); await form(w); await w.find('.inference-form').trigger('submit'); const signal = vi.mocked(jobApi.infer).mock.calls[0][3]!
  if (mode === 'model') await w.findAll('.inference-form select')[1].setValue('onnx-b')
  else if (mode === 'project') await w.setProps({ project: { ...project, id: 'p-new' } })
  else w.unmount()
  pending.resolve({ job_id: 'late-job', state: 'queued' }); await flushPromises(); expect(signal.aborted).toBe(true); expect(jobApi.detail).not.toHaveBeenCalledWith('late-job', expect.anything())
  if (mode !== 'unmount') { expect(w.text()).not.toContain('late-job'); if (mode === 'model') expect((w.findAll('.inference-form select')[1].element as HTMLSelectElement).value).toBe('onnx-b') }
})
it('uses the original key when returning to parameters whose request was aborted', async () => {
  mocks(); const pending = deferred<JobAccepted>(); vi.mocked(jobApi.infer).mockReturnValueOnce(pending.promise)
  const w = create(); await flushPromises(); await form(w); await w.find('.inference-form').trigger('submit'); await w.findAll('.inference-form select')[1].setValue('onnx-b'); await w.findAll('.inference-form select')[1].setValue('onnx-a'); await flushPromises(); await w.find('.inference-form').trigger('submit'); await flushPromises()
  expect(vi.mocked(jobApi.infer).mock.calls[0][2]).toBe(vi.mocked(jobApi.infer).mock.calls[1][2]); pending.resolve({ job_id: 'obsolete', state: 'queued' }); await flushPromises(); expect(w.text()).not.toContain('obsolete')
})
it('creates an explicit failed-job retry with a new but stable key across lost response and remount', async () => {
  mocks(); const old = inferenceRequests('u', 'p', () => {}).get(inferParams); old.job_id = 'infer-a'; inferenceRequests('u', 'p', () => {}).save(old, true)
  const originalDetail = vi.mocked(jobApi.detail).getMockImplementation()!; vi.mocked(jobApi.detail).mockImplementation(async (id, signal) => id === 'infer-a' ? inferJob(id, 'failed') : originalDetail(id, signal)); vi.mocked(jobApi.infer).mockRejectedValueOnce(new Error('lost retry response'))
  const first = create(); await flushPromises(); await button(first, '重新推理（新任务）').trigger('click'); await flushPromises(); const retry = vi.mocked(jobApi.infer).mock.calls[0]
  expect(retry[2]).not.toBe(old.key); expect(retry[4]).toBe('infer-a'); first.unmount()
  const second = create(); await flushPromises(); await second.find('.inference-form').trigger('submit'); await flushPromises()
  expect(vi.mocked(jobApi.infer).mock.calls[1][2]).toBe(retry[2]); expect(vi.mocked(jobApi.infer).mock.calls[1][4]).toBe('infer-a'); expect(second.text()).toContain('已接收任务 infer-new')
})
it('does not create another retry when retry acceptance is known but detail is unavailable', async () => {
  mocks(); const originalDetail = vi.mocked(jobApi.detail).getMockImplementation()!; vi.mocked(jobApi.detail).mockImplementation(async (id, signal) => id === 'infer-a' ? inferJob(id, 'failed') : id === 'infer-new' ? Promise.reject(new Error('detail offline')) : originalDetail(id, signal))
  const first = create(); await flushPromises(); await button(first, '重新推理（新任务）').trigger('click'); await flushPromises(); first.unmount()
  const second = create(); await flushPromises(); await second.find('.inference-form').trigger('submit'); await flushPromises(); expect(jobApi.infer).toHaveBeenCalledTimes(1)
  await button(second, 'infer-a · running').trigger('click'); await flushPromises(); await button(second, '重新推理（新任务）').trigger('click'); await flushPromises(); expect(jobApi.infer).toHaveBeenCalledTimes(1)
})
it('ignores a stale log failure after a new job is selected', async () => {
  mocks(); vi.mocked(jobApi.list).mockResolvedValue(page([inferJob(), inferJob('infer-b')]))
  const pending = deferred<Awaited<ReturnType<typeof jobApi.logs>>>(); vi.mocked(jobApi.logs).mockReturnValueOnce(pending.promise)
  const w = create(); await flushPromises(); const signal = vi.mocked(jobApi.logs).mock.calls[0][2]!
  await button(w, 'infer-b · running').trigger('click'); await flushPromises(); pending.reject(new ApiClientError(401, 'STALE', 'stale error')); await flushPromises()
  expect(signal.aborted).toBe(true); expect(w.find('.identity').text()).toBe('infer-b'); expect(w.emitted('error')).toBeUndefined(); expect(w.text()).not.toContain('stale error')
})
it('backs off on disconnection and incrementally deduplicates bounded logs on reconnection', async () => {
  mocks(); vi.mocked(jobApi.logs).mockResolvedValueOnce({ items: [{ seq: 1, at: date, level: 'info', text: 'first log' }], next_cursor: 'cursor-one', eof: false, job_state: 'running' }).mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ items: Array.from({ length: 502 }, (_, i) => ({ seq: i + 1, at: date, level: 'info', text: `log-${i + 1}` })), next_cursor: 'cursor-final', eof: true, job_state: 'succeeded' })
  const w = create(); await flushPromises(); await vi.advanceTimersByTimeAsync(2000); await flushPromises(); expect(w.text()).toContain('将自动重试'); await vi.advanceTimersByTimeAsync(3000); expect(jobApi.logs).toHaveBeenCalledTimes(2); await vi.advanceTimersByTimeAsync(1000); await flushPromises()
  expect(vi.mocked(jobApi.logs).mock.calls[2][1]).toBe('cursor-one'); expect(w.findAll('.job-log li')).toHaveLength(500); expect(w.text()).toContain('log-502'); expect(w.text()).not.toContain('first log'); expect(w.text()).toContain('已读取最终日志')
  await vi.advanceTimersByTimeAsync(2000); expect(jobApi.logs).toHaveBeenCalledTimes(3)
})
it.each(['succeeded', 'cancelled'] as const)('uses the server terminal winner when cancellation races with %s', async state => {
  mocks(); const w = create(); await flushPromises(); const originalDetail = vi.mocked(jobApi.detail).getMockImplementation()!
  vi.mocked(jobApi.cancel).mockResolvedValue(inferJob('infer-a', state)); vi.mocked(jobApi.detail).mockImplementation(async (id, signal) => id === 'infer-a' ? inferJob(id, state) : originalDetail(id, signal))
  await button(w, '取消推理').trigger('click'); await flushPromises(); expect(w.find('h3').text()).toContain(state); expect(button(w, '取消推理').attributes('disabled')).toBeDefined()
})
it('does not label a cancelling job cancelled before the server confirms it', async () => {
  mocks(); const w = create(); await flushPromises(); vi.mocked(jobApi.cancel).mockResolvedValue(inferJob('infer-a', 'cancelling')); vi.mocked(jobApi.detail).mockResolvedValue(inferJob('infer-a', 'cancelling'))
  await button(w, '取消推理').trigger('click'); await flushPromises(); expect(w.find('h3').text()).toContain('cancelling'); expect(button(w, '正在停止推理…').attributes('disabled')).toBeDefined()
})
it('ignores late cancellation when the user selects another job', async () => {
  mocks(); vi.mocked(jobApi.list).mockResolvedValue(page([inferJob(), inferJob('infer-b')])); const pending = deferred<Job>(); vi.mocked(jobApi.cancel).mockReturnValue(pending.promise)
  const w = create(); await flushPromises(); await button(w, '取消推理').trigger('click'); await button(w, 'infer-b · running').trigger('click'); await flushPromises(); pending.resolve(inferJob('infer-a', 'cancelled')); await flushPromises(); expect(w.find('.identity').text()).toBe('infer-b')
})
it('retains a failed mutation warning when later reads recover', async () => {
  mocks(); vi.mocked(jobApi.cancel).mockRejectedValue(new ApiClientError(503, 'OFFLINE', '取消结果未确认')); const w = create(); await flushPromises(); await button(w, '取消推理').trigger('click'); await flushPromises(); await vi.advanceTimersByTimeAsync(2000); await flushPromises(); expect(w.text()).toContain('取消结果未确认'); expect(w.find('h3').text()).toContain('running')
})
it.each(['list', 'upload', 'submit', 'preview'])('propagates active %s 401 to invalidate the session', async operation => {
  mocks(); const failure = new ApiClientError(401, 'SESSION_EXPIRED', '会话已失效')
  if (operation === 'list') vi.mocked(jobApi.list).mockRejectedValue(failure)
  if (operation === 'preview') { succeeded(); vi.mocked(inferenceApi.preview).mockRejectedValue(failure) }
  const w = create(); await flushPromises()
  if (operation === 'upload') { vi.mocked(inferenceApi.upload).mockRejectedValue(failure); await selectFile(w); await w.find('.inference-upload').trigger('submit'); await flushPromises() }
  if (operation === 'submit') { vi.mocked(jobApi.infer).mockRejectedValue(failure); await form(w); await w.find('.inference-form').trigger('submit'); await flushPromises() }
  expect(w.emitted('error')?.[0]).toEqual([failure])
})
it('rejects foreign result bindings and never fetches an API-supplied external URL', async () => {
  mocks(); succeeded(); vi.mocked(inferenceApi.result).mockResolvedValue({ ...inferenceResult(), image_url: 'https://example.invalid/image' }); const w = create(); await flushPromises(); expect(inferenceApi.preview).not.toHaveBeenCalled(); expect(w.find('svg').exists()).toBe(false); expect(w.find('a').exists()).toBe(false)
})
it('cleans timers, outstanding read signals, and blob URLs on unmount', async () => {
  mocks(); succeeded(); const w = create(); await flushPromises(); const signal = vi.mocked(inferenceApi.preview).mock.calls[0][1]!; const reads = vi.mocked(jobApi.list).mock.calls.length
  w.unmount(); expect(signal.aborted).toBe(true); expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:synthetic-preview'); await vi.advanceTimersByTimeAsync(60000); expect(jobApi.list).toHaveBeenCalledTimes(reads)
})
it('does not create a stale preview URL after switching the selected job', async () => {
  mocks(); succeeded(); vi.mocked(jobApi.list).mockResolvedValue(page([inferJob('infer-a', 'succeeded'), inferJob('infer-b')]))
  const pending = deferred<Blob>(); vi.mocked(inferenceApi.preview).mockReturnValueOnce(pending.promise)
  const w = create(); await flushPromises(); vi.mocked(jobApi.detail).mockResolvedValue(inferJob('infer-b')); await button(w, 'infer-b · running').trigger('click'); await flushPromises(); pending.resolve(new Blob(['late'])); await flushPromises()
  expect(URL.createObjectURL).not.toHaveBeenCalled(); expect(w.find('svg').exists()).toBe(false)
})
it('keeps a stable in-memory key and warns if session storage is unavailable', async () => {
  mocks(); vi.stubGlobal('sessionStorage', { getItem: () => null, setItem: () => { throw new Error('quota') } }); vi.mocked(jobApi.infer).mockRejectedValue(new Error('offline'))
  const w = create(); await flushPromises(); await form(w); await w.find('.inference-form').trigger('submit'); await flushPromises(); await w.find('.inference-form').trigger('submit'); await flushPromises()
  expect(w.text()).toContain('无法可靠保存恢复标识'); expect(vi.mocked(jobApi.infer).mock.calls[0][2]).toBe(vi.mocked(jobApi.infer).mock.calls[1][2])
})

it.each(['project', 'backend', 'provider', 'threshold'])('rejects a result whose %s does not match the selected frozen job', async mismatch => {
  mocks(); succeeded(); const value = inferenceResult()
  if (mismatch === 'project') value.provenance.project_id = 'elsewhere'
  if (mismatch === 'backend') value.backend = 'pt'
  if (mismatch === 'provider') value.provider = 'pytorch_cpu'
  if (mismatch === 'threshold') value.params.confidence = .9
  vi.mocked(inferenceApi.result).mockResolvedValue(value); const w = create(); await flushPromises()
  expect(inferenceApi.preview).not.toHaveBeenCalled(); expect(w.find('.verified-inference').exists()).toBe(false); expect(w.find('a').exists()).toBe(false)
})
it('can refresh a stalled read and ignores its late inventory', async () => {
  mocks(); const pending = deferred<Awaited<ReturnType<typeof jobApi.artifacts>>>(); vi.mocked(jobApi.artifacts).mockReturnValueOnce(pending.promise)
  const w = create(); await flushPromises(); const signal = vi.mocked(jobApi.artifacts).mock.calls[0][1]!
  await button(w, '刷新推理状态').trigger('click'); await flushPromises(); pending.resolve(page<Artifact>([{ ...onnx(), id: 'stale-model' }])); await flushPromises()
  expect(signal.aborted).toBe(true); expect(w.text()).not.toContain('stale-model'); expect(w.findAll('.inference-form select')[1].findAll('option')).toHaveLength(3)
})
it('reads all artifact pages without exposing an incomplete model inventory', async () => {
  mocks(); vi.mocked(jobApi.artifacts).mockResolvedValueOnce({ items: [pt()], total: 3, page: 1, page_size: 1 }).mockResolvedValueOnce({ items: [onnx(), imageInput()], total: 3, page: 2, page_size: 2 })
  const w = create(); await flushPromises(); expect(vi.mocked(jobApi.artifacts).mock.calls.map(c => c[2])).toEqual([1, 2]); expect(w.findAll('.inference-form select')[1].findAll('option')).toHaveLength(2)
  vi.mocked(jobApi.artifacts).mockResolvedValue({ items: [], total: 3, page: 1, page_size: 100 }); await button(w, '刷新推理状态').trigger('click'); await flushPromises(); expect(w.text()).toContain('将自动重试')
})
it.each(['backend', 'input', 'threshold'])('ignores a late submit after changing %s', async change => {
  mocks(); vi.mocked(jobApi.artifacts).mockResolvedValue(page<Artifact>([pt(), onnx(), imageInput(), imageInput('image-b')]))
  const pending = deferred<JobAccepted>(); vi.mocked(jobApi.infer).mockReturnValueOnce(pending.promise)
  const w = create(); await flushPromises(); await form(w); await w.find('.inference-form').trigger('submit')
  if (change === 'backend') await w.findAll('.inference-form select')[0].setValue('pt')
  else if (change === 'input') await w.findAll('.inference-form select')[2].setValue('image-b')
  else await w.findAll('.inference-form input')[0].setValue('.75')
  pending.resolve({ job_id: 'old-params-job', state: 'queued' }); await flushPromises()
  expect(vi.mocked(jobApi.infer).mock.calls[0][3]?.aborted).toBe(true); expect(w.text()).not.toContain('old-params-job'); expect(jobApi.detail).not.toHaveBeenCalledWith('old-params-job', expect.anything())
})
it.each(['archive', 'capability', 'missing-model'])('recovers only the saved pending key and frozen parameters after %s blocks new jobs', async mode => {
  mocks()
  const saved = inferenceRequests('u', 'p', () => {}).get({ ...inferParams, confidence: .6 }, 'failed-original')
  const random = vi.spyOn(crypto, 'randomUUID')
  if (mode === 'missing-model') vi.mocked(jobApi.artifacts).mockResolvedValue(page([]))
  const w = create(mode === 'archive' ? { project: { ...project, archived_at: date } } : mode === 'capability' ? { onnxCapability: { ...capability, available: false } } : {})
  await flushPromises(); expect(w.find('.inference-form button').attributes('disabled')).toBeDefined()
  await button(w, '恢复未确认提交（同一请求）').trigger('click'); await flushPromises()
  expect(jobApi.infer).toHaveBeenCalledTimes(1); expect(vi.mocked(jobApi.infer).mock.calls[0]).toEqual(['p', saved.params, saved.key, expect.any(AbortSignal), 'failed-original'])
  expect(random).not.toHaveBeenCalled(); expect(w.text()).toContain('已接收任务 infer-new')
})
it('shows a replay rejection without claiming a task was restored when the original was never accepted', async () => {
  mocks(); const saved = inferenceRequests('u', 'p', () => {}).get(inferParams)
  vi.mocked(jobApi.infer).mockRejectedValue(new ApiClientError(409, 'PROJECT_ARCHIVED', '项目已归档，原请求未被接收，不能创建任务'))
  const w = create({ project: { ...project, archived_at: date } }); await flushPromises(); await button(w, '恢复未确认提交（同一请求）').trigger('click'); await flushPromises()
  expect(w.text()).toContain('原请求未被接收，不能创建任务'); expect(w.text()).not.toContain('已接收任务'); expect(w.find('.inference-detail').exists()).toBe(false)
  await button(w, '恢复未确认提交（同一请求）').trigger('click'); await flushPromises(); expect(vi.mocked(jobApi.infer).mock.calls.map(c => c[2])).toEqual([saved.key, saved.key])
})
it('propagates 401 from recovery without assuming old authorization still applies', async () => {
  mocks(); inferenceRequests('u', 'p', () => {}).get(inferParams)
  const failure = new ApiClientError(401, 'SESSION_EXPIRED', '会话已失效'); vi.mocked(jobApi.infer).mockRejectedValue(failure)
  const w = create(); await flushPromises(); await button(w, '恢复未确认提交（同一请求）').trigger('click'); await flushPromises()
  expect(w.emitted('error')?.[0]).toEqual([failure]); expect(w.text()).not.toContain('已接收任务')
})
it.each(['form-first', 'recovery-first'])('serializes the form and recovery buttons (%s) without creating a new key', async mode => {
  mocks(); const saved = inferenceRequests('u', 'p', () => {}).get(inferParams), pending = deferred<JobAccepted>(); vi.mocked(jobApi.infer).mockReturnValue(pending.promise)
  const w = create(); await flushPromises()
  if (mode === 'form-first') { await w.find('.inference-form').trigger('submit'); await button(w, '恢复未确认提交（同一请求）').trigger('click') }
  else { await button(w, '恢复未确认提交（同一请求）').trigger('click'); await w.find('.inference-form').trigger('submit') }
  expect(jobApi.infer).toHaveBeenCalledTimes(1); expect(vi.mocked(jobApi.infer).mock.calls[0][2]).toBe(saved.key)
  pending.resolve({ job_id: 'recovered', state: 'queued' }); await flushPromises(); expect(w.text()).toContain('已接收任务 recovered')
})
it.each(['noop', 'threshold-roundtrip', 'model-roundtrip', 'backend-roundtrip', 'remount-after-edit'])('retains retry source and key after %s while the POST response is unconfirmed', async edit => {
  mocks(); const original = vi.mocked(jobApi.detail).getMockImplementation()!
  vi.mocked(jobApi.detail).mockImplementation(async (id, signal) => id === 'infer-a' ? inferJob(id, 'failed') : original(id, signal))
  vi.mocked(jobApi.infer).mockRejectedValueOnce(new Error('lost retry response'))
  let w = create(); await flushPromises(); await button(w, '重新推理（新任务）').trigger('click'); await flushPromises()
  const first = vi.mocked(jobApi.infer).mock.calls[0]
  if (edit === 'noop') await w.findAll('.inference-form input')[0].trigger('input')
  if (edit === 'threshold-roundtrip' || edit === 'remount-after-edit') { await w.findAll('.inference-form input')[0].setValue('.8'); expect(button(w, '恢复未确认提交（同一请求）').exists()).toBe(true); await w.findAll('.inference-form input')[0].setValue('.25') }
  if (edit === 'model-roundtrip') { await w.findAll('.inference-form select')[1].setValue('onnx-b'); expect(w.find('.pending-recovery').text()).toContain('重试来源 infer-a'); await w.findAll('.inference-form select')[1].setValue('onnx-a') }
  if (edit === 'backend-roundtrip') { await w.findAll('.inference-form select')[0].setValue('pt'); await w.findAll('.inference-form select')[0].setValue('onnx'); await w.findAll('.inference-form select')[1].setValue('onnx-a') }
  if (edit === 'remount-after-edit') { w.unmount(); w = create(); await flushPromises() }
  await w.find('.inference-form').trigger('submit'); await flushPromises()
  expect(jobApi.infer).toHaveBeenCalledTimes(2); const second = vi.mocked(jobApi.infer).mock.calls[1]
  expect(second[2]).toBe(first[2]); expect(second[4]).toBe('infer-a'); expect(second[1]).toEqual(first[1])
})
it('keeps recovery discoverable after editing and replays its original params without overwriting the new form', async () => {
  mocks(); const saved = inferenceRequests('u', 'p', () => {}).get(inferParams, 'failed-original')
  const w = create(); await flushPromises(); await w.findAll('.inference-form select')[1].setValue('onnx-b'); await w.findAll('.inference-form input')[0].setValue('.8')
  expect(w.find('.pending-recovery').text()).toContain('confidence 0.25'); await button(w, '恢复未确认提交（同一请求）').trigger('click'); await flushPromises()
  expect(vi.mocked(jobApi.infer).mock.calls[0]).toEqual(['p', saved.params, saved.key, expect.any(AbortSignal), 'failed-original'])
  expect((w.findAll('.inference-form select')[1].element as HTMLSelectElement).value).toBe('onnx-b'); expect((w.findAll('.inference-form input')[0].element as HTMLInputElement).value).toBe('0.8')
})
it('isolates saved requests by authenticated actor even when both actors access the same project', async () => {
  mocks(); const saved = inferenceRequests('u', 'p', () => {}).get(inferParams, 'failed-owner')
  const w = create(); await flushPromises(); expect(w.find('.pending-recovery').exists()).toBe(true)
  await w.setProps({ userId: 'admin' }); await flushPromises(); expect(w.find('.pending-recovery').exists()).toBe(false)
  await form(w); await w.find('.inference-form').trigger('submit'); await flushPromises()
  expect(vi.mocked(jobApi.infer).mock.calls[0][2]).not.toBe(saved.key); expect(vi.mocked(jobApi.infer).mock.calls[0][4]).toBeUndefined()
  await w.setProps({ userId: 'u' }); await flushPromises(); expect(w.find('.pending-recovery').text()).toContain('failed-owner')
  await button(w, '恢复未确认提交（同一请求）').trigger('click'); await flushPromises(); expect(vi.mocked(jobApi.infer).mock.calls[1][2]).toBe(saved.key); expect(vi.mocked(jobApi.infer).mock.calls[1][4]).toBe('failed-owner')
})
it('does not adopt legacy actor-less recovery records', async () => {
  mocks(); sessionStorage.setItem('edgevision.inference.v1:p:last', JSON.stringify({ params: inferParams, key: crypto.randomUUID(), source_job_id: 'unknown-actor' }))
  const w = create(); await flushPromises(); expect(w.find('.pending-recovery').exists()).toBe(false); expect(w.text()).not.toContain('unknown-actor')
})
