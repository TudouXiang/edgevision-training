// @vitest-environment happy-dom
// All records below are synthetic API-shaped fixtures, not execution evidence.
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import ExportPanel from './ExportPanel.vue'
import { ApiClientError, jobApi } from '../api'
import type { Artifact, Job, Project } from '../api'

const date = '2026-11-04T00:00:00Z', sha = 'a'.repeat(64)
const project: Project = { id: 'p', owner_id: 'u', name: 'P', description: '', archived_at: null, created_at: date, updated_at: date }
const capability = { available: true, reason: null, reason_code: null, detected_version: '1.31.1' }
const job = (id = 'export-a', state: Job['state'] = 'running', project_id = 'p', kind: Job['kind'] = 'export_onnx'): Job => ({ id, project_id, created_by: 'u', kind, state, params_schema_version: 1, created_at: date, started_at: date, finished_at: null, error_code: null, source_job_id: null })
const params = { dataset_id: 'd', experiment_name: 'Fixture training', base_model: 'yolo11n.pt', device: 'cpu', epochs: 1, batch: 1, imgsz: 320, seed: 0, learning_rate: .01 } as const
const training = { schema_version: 1, dataset_id: 'd', dataset_version: 1, archive_sha256: sha, snapshot_sha256: sha, report_artifact_id: 'report', report_sha256: sha, counts: { images: 8 }, classes: ['object'], base_model_sha256: sha, base_manifest_sha256: sha, params, runtime_binding: sha, code_version: sha } as const
const versions = { torch: '2.15.0+cpu', torchvision: '0.29.2+cpu', ultralytics: '8.4.202' } as const
function pt(id = 'pt-a', job_id = 'train-a', project_id = 'p'): Extract<Artifact, { kind: 'pt_best' | 'pt_last' }> {
  return { id, project_id, job_id, kind: 'pt_best', format: 'pt', sha256: sha, size_bytes: 100, metadata_schema_version: 1, validation_state: 'passed', created_at: date,
    metadata: { schema_version: 1, task: 'detection', architecture: 'yolo11n', classes: ['object'], provenance: { ...training, classes: ['object'] }, validation_scope: 'weights_only_detection_checkpoint', runtime: { versions, optimizer_steps: 1, completed_epochs: 1, safe_load_count: 2, threads: 2, device: 'cpu', effective: { optimizer: 'SGD', lr0: .01, lrf: .01, warmup_epochs: 0, warmup_bias_lr: 0, warmup_momentum: .8, momentum: .937, weight_decay: .0005, nbs: 64, seed: 0, batch: 1, epochs: 1, imgsz: 320, device: 'cpu', workers: 0, amp: false, plots: false, cache: false, deterministic: true } } } }
}
function onnx(): Extract<Artifact, { kind: 'onnx' }> {
  return { id: 'onnx-a', project_id: 'p', job_id: 'export-a', kind: 'onnx', format: 'onnx', sha256: sha, size_bytes: 200, metadata_schema_version: 1, validation_state: 'passed', created_at: date,
    metadata: { schema_version: 1, task: 'detection', architecture: 'yolo11n', classes: ['object'], validation_scope: 'checker_ort_raw_tensor_equivalence', validation_sha256: sha,
      provenance: { schema_version: 1, job_id: 'export-a', run_id: 'run-a', input_sha256: sha, parent_artifact_id: 'pt-a', source_job_id: 'train-a', source_sha256: sha, source_size_bytes: 100, source_metadata_sha256: sha, source_training_input_sha256: sha, training: { ...training, classes: ['object'] }, runtime_binding: sha, code_version: sha },
      validation: { schema_version: 1, job_id: 'export-a', run_id: 'run-a', input_sha256: sha, source_sha256: sha, original_graph_sha256: sha, model_sha256: sha, model_size_bytes: 200, classes: ['object'], input_name: 'images', input_shape: [1, 3, 640, 640], output_name: 'output0', output_shape: [1, 5, 8400], dtype: 'float32', tensor_protocol: 'rgb-fixed-v1', atol: .0001, rtol: .0001, checker_passed: true,
        runtime: { versions: { ...versions, onnx: '1.23.2', onnxruntime: '1.31.1' }, provider: 'CPUExecutionProvider', device: 'cpu', threads: 2, opset: 18, ir_version: 8, precision: 'fp32', dynamic: false, simplify: false, nms: false },
        samples: (['zeros', 'gradient', 'pattern'] as const).map(name => ({ name, input_sha256: sha, pt_sha256: sha, ort_sha256: sha, max_absolute_error: 0, max_tolerance_ratio: 0, elements: 42000, passed: true })) } } }
}
const page = <T,>(items: T[]) => ({ items, total: items.length, page: 1, page_size: 100 })
function deferred<T>() { let resolve!: (value: T) => void, reject!: (reason: unknown) => void; const promise = new Promise<T>((ok, no) => { resolve = ok; reject = no }); return { resolve, reject, promise } }
const wrappers: ReturnType<typeof mount>[] = []
function create(extra = {}) { const wrapper = mount(ExportPanel, { props: { project, capability, ...extra } }); wrappers.push(wrapper); return wrapper }
function button(wrapper: ReturnType<typeof mount>, text: string) { return wrapper.findAll('button').find(item => item.text() === text)! }
function mocks() {
  vi.useFakeTimers()
  vi.spyOn(jobApi, 'list').mockResolvedValue(page([job()]))
  vi.spyOn(jobApi, 'detail').mockImplementation(async id => id.startsWith('train') ? job(id, 'succeeded', 'p', 'train') : job(id))
  vi.spyOn(jobApi, 'artifacts').mockResolvedValue(page([pt(), pt('pt-b')]))
  vi.spyOn(jobApi, 'logs').mockResolvedValue({ items: [], next_cursor: null, eof: false, job_state: 'running' })
  vi.spyOn(jobApi, 'exportOnnx').mockResolvedValue({ job_id: 'new-export', state: 'queued' })
  vi.spyOn(jobApi, 'cancel').mockImplementation(async id => job(id, 'cancelled'))
}
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()); vi.restoreAllMocks(); vi.useRealTimers(); sessionStorage.clear() })

it('renders succeeded API state, drains real logs, and only links passed ONNX for that job', async () => {
  mocks(); vi.mocked(jobApi.detail).mockImplementation(async id => id.startsWith('train') ? job(id, 'succeeded', 'p', 'train') : job(id, 'succeeded'))
  vi.mocked(jobApi.artifacts).mockResolvedValue(page([pt(), onnx(), { ...onnx(), id: 'other-job', job_id: 'elsewhere' }]))
  vi.mocked(jobApi.logs).mockResolvedValue({ items: [{ seq: 1, level: 'info', text: 'Actual API log fixture', at: date }], next_cursor: '1', eof: true, job_state: 'succeeded' })
  const wrapper = create(); await flushPromises()
  expect(wrapper.find('h3').text()).toContain('succeeded'); expect(wrapper.text()).toContain('CPUExecutionProvider'); expect(wrapper.text()).toContain('1 × 3 × 640 × 640 / 1 × 5 × 8400'); expect(wrapper.text()).toContain('Actual API log fixture'); expect(wrapper.text()).toContain('已读取最终日志')
  expect(wrapper.findAll('a')).toHaveLength(1); expect(wrapper.find('a').attributes('href')).toBe('/api/v1/artifacts/onnx-a/download')
  await vi.advanceTimersByTimeAsync(2000); expect(jobApi.logs).toHaveBeenCalledTimes(1)
})
it('excludes foreign, unverified, and failed-training models and blocks unsupported capability', async () => {
  mocks(); vi.mocked(jobApi.artifacts).mockResolvedValue(page([pt(), pt('foreign', 'train-a', 'foreign'), { ...pt('bad'), validation_state: 'failed' }, pt('failed-training', 'failed')]))
  vi.mocked(jobApi.detail).mockImplementation(async id => id === 'failed' ? job(id, 'failed', 'p', 'train') : id.startsWith('train') ? job(id, 'succeeded', 'p', 'train') : job(id))
  const wrapper = create({ capability: { ...capability, available: false, reason: '工具链尚未验证' } }); await flushPromises()
  expect(wrapper.findAll('option').map(option => option.attributes('value'))).toEqual(['', 'pt-a'])
  await wrapper.find('select').setValue('pt-a'); await wrapper.find('form').trigger('submit')
  expect(jobApi.exportOnnx).not.toHaveBeenCalled(); expect(wrapper.text()).toContain('工具链尚未验证')
})
it('submits fixed params once on repeated clicks and retains accepted key', async () => {
  mocks(); const pending = deferred<{ job_id: string; state: 'queued' }>(); vi.mocked(jobApi.exportOnnx).mockReturnValue(pending.promise)
  const wrapper = create(); await flushPromises(); await wrapper.find('select').setValue('pt-a'); await flushPromises()
  await wrapper.find('form').trigger('submit'); await wrapper.find('form').trigger('submit')
  expect(jobApi.exportOnnx).toHaveBeenCalledTimes(1)
  expect(vi.mocked(jobApi.exportOnnx).mock.calls[0][1]).toEqual({ model_artifact_id: 'pt-a', batch: 1, imgsz: 640, precision: 'fp32' })
  pending.resolve({ job_id: 'new-export', state: 'queued' }); await flushPromises(); await wrapper.find('form').trigger('submit')
  expect(jobApi.exportOnnx).toHaveBeenCalledTimes(1); expect(wrapper.text()).toContain('new-export')
})
it('retries a lost submit response with the same idempotency key', async () => {
  mocks(); vi.mocked(jobApi.exportOnnx).mockRejectedValueOnce(new Error('offline'))
  const wrapper = create(); await flushPromises(); await wrapper.find('select').setValue('pt-a'); await flushPromises()
  await wrapper.find('form').trigger('submit'); await flushPromises(); await wrapper.find('form').trigger('submit'); await flushPromises()
  const calls = vi.mocked(jobApi.exportOnnx).mock.calls; expect(calls).toHaveLength(2); expect(calls[0][2]).toBe(calls[1][2])
})
it('does not duplicate acceptance when the first detail read fails', async () => {
  mocks(); const detail = vi.mocked(jobApi.detail).getMockImplementation()!
  vi.mocked(jobApi.detail).mockImplementation((id, signal) => id === 'new-export' ? Promise.reject(new Error('offline')) : detail(id, signal))
  const wrapper = create(); await flushPromises(); await wrapper.find('select').setValue('pt-a'); await flushPromises()
  await wrapper.find('form').trigger('submit'); await flushPromises(); await wrapper.find('form').trigger('submit')
  expect(jobApi.exportOnnx).toHaveBeenCalledTimes(1); expect(wrapper.text()).toContain('已接收任务 new-export')
})
it('keeps newer model selection after late submission resolves', async () => {
  mocks(); const pending = deferred<{ job_id: string; state: 'queued' }>(); vi.mocked(jobApi.exportOnnx).mockReturnValue(pending.promise)
  const wrapper = create(); await flushPromises(); await wrapper.find('select').setValue('pt-a'); await flushPromises()
  await wrapper.find('form').trigger('submit'); await wrapper.find('select').setValue('pt-b'); await flushPromises()
  pending.resolve({ job_id: 'new-export', state: 'queued' }); await flushPromises()
  expect(wrapper.find('select').element.value).toBe('pt-b'); expect(wrapper.find('h3').exists()).toBe(false)
  expect(jobApi.detail).not.toHaveBeenCalledWith('new-export', expect.anything())
})
it('keeps newer job selection after stale details, logs and errors arrive', async () => {
  mocks(); vi.mocked(jobApi.list).mockResolvedValue(page([job(), job('export-b')]))
  const pending = deferred<Awaited<ReturnType<typeof jobApi.logs>>>(); vi.mocked(jobApi.logs).mockReturnValueOnce(pending.promise)
  const wrapper = create(); await flushPromises()
  await button(wrapper, 'export-b · running').trigger('click'); await flushPromises()
  pending.reject(new ApiClientError(401, 'STALE', 'stale error')); await flushPromises()
  expect(wrapper.find('.identity').text()).toBe('export-b'); expect(wrapper.text()).not.toContain('stale error'); expect(wrapper.emitted('error')).toBeUndefined()
})
it('ignores late cancellation after another job is selected', async () => {
  mocks(); vi.mocked(jobApi.list).mockResolvedValue(page([job(), job('export-b')]))
  const pending = deferred<Job>(); vi.mocked(jobApi.cancel).mockReturnValue(pending.promise)
  const wrapper = create(); await flushPromises(); await button(wrapper, '取消导出').trigger('click')
  await button(wrapper, 'export-b · running').trigger('click'); await flushPromises(); pending.resolve(job('export-a', 'cancelled')); await flushPromises()
  expect(wrapper.find('.identity').text()).toBe('export-b'); expect(wrapper.find('h3').text()).toContain('running')
})
it('shows cancelling until the API confirms a terminal state', async () => {
  mocks(); vi.mocked(jobApi.cancel).mockResolvedValue(job('export-a', 'cancelling'))
  const wrapper = create(); await flushPromises(); vi.mocked(jobApi.detail).mockResolvedValue(job('export-a', 'cancelling'))
  await button(wrapper, '取消导出').trigger('click'); await flushPromises()
  expect(wrapper.find('h3').text()).toContain('cancelling'); expect(button(wrapper, '正在停止导出…').attributes('disabled')).toBeDefined()
  vi.mocked(jobApi.detail).mockResolvedValue(job('export-a', 'cancelled')); await vi.advanceTimersByTimeAsync(2000); await flushPromises()
  expect(wrapper.find('h3').text()).toContain('cancelled'); expect(wrapper.find('a').exists()).toBe(false)
})
it('backs off poll failures and recovers without inventing logs or progress', async () => {
  mocks(); vi.mocked(jobApi.logs).mockRejectedValueOnce(new Error('offline'))
  const wrapper = create(); await flushPromises(); expect(wrapper.find('[role=alert]').text()).toContain('将自动重试')
  await vi.advanceTimersByTimeAsync(3000); expect(jobApi.logs).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(1000); await flushPromises(); expect(jobApi.logs).toHaveBeenCalledTimes(2); expect(wrapper.find('[role=alert]').exists()).toBe(false)
  expect(wrapper.text()).toContain('暂无日志，未合成进度')
})
it('rejects stale project reads and aborts outstanding work on unmount', async () => {
  mocks(); const pending = deferred<Awaited<ReturnType<typeof jobApi.artifacts>>>(); vi.mocked(jobApi.artifacts).mockReturnValueOnce(pending.promise)
  const wrapper = create(); await flushPromises(); const oldSignal = vi.mocked(jobApi.artifacts).mock.calls[0][1]!
  vi.mocked(jobApi.list).mockResolvedValue(page([])); vi.mocked(jobApi.artifacts).mockResolvedValue(page([]))
  await wrapper.setProps({ project: { ...project, id: 'p-new' } }); await flushPromises(); pending.resolve(page([pt()])); await flushPromises()
  expect(oldSignal.aborted).toBe(true); expect(wrapper.findAll('option')).toHaveLength(1); expect(wrapper.find('h3').exists()).toBe(false)
  const calls = vi.mocked(jobApi.list).mock.calls.length; wrapper.unmount(); await vi.advanceTimersByTimeAsync(30000)
  expect(jobApi.list).toHaveBeenCalledTimes(calls)
})
it('reconstructs history and terminal output on page remount', async () => {
  mocks(); vi.mocked(jobApi.list).mockResolvedValue(page([job('export-a', 'succeeded')])); vi.mocked(jobApi.detail).mockImplementation(async id => id.startsWith('train') ? job(id, 'succeeded', 'p', 'train') : job(id, 'succeeded'))
  vi.mocked(jobApi.artifacts).mockResolvedValue(page([pt(), onnx()])); vi.mocked(jobApi.logs).mockResolvedValue({ items: [], next_cursor: null, eof: true, job_state: 'succeeded' })
  const original = create(); await flushPromises(); original.unmount()
  const reloaded = create(); await flushPromises(); expect(reloaded.find('a').attributes('href')).toBe('/api/v1/artifacts/onnx-a/download'); expect(jobApi.exportOnnx).not.toHaveBeenCalled()
})
it('retains a failed cancellation warning while later reads recover', async () => {
  mocks(); vi.mocked(jobApi.cancel).mockRejectedValue(new ApiClientError(503, 'OFFLINE', '取消请求失败'))
  const wrapper = create(); await flushPromises(); await button(wrapper, '取消导出').trigger('click'); await flushPromises()
  expect(wrapper.find('[role=alert]').text()).toBe('取消请求失败'); expect(wrapper.find('h3').text()).toContain('running')
  await vi.advanceTimersByTimeAsync(2000); await flushPromises(); expect(wrapper.find('[role=alert]').text()).toBe('取消请求失败')
})
it('does not expose any download while an export is failed or cancelled', async () => {
  mocks(); vi.mocked(jobApi.artifacts).mockResolvedValue(page([pt(), onnx()])); vi.mocked(jobApi.detail).mockImplementation(async id => id.startsWith('train') ? job(id, 'succeeded', 'p', 'train') : job(id, 'failed'))
  const wrapper = create(); await flushPromises(); expect(wrapper.find('h3').text()).toContain('failed'); expect(wrapper.find('a').exists()).toBe(false)
})
it('reuses the server idempotency key after route remount or reload loses a submit response', async () => {
  mocks(); const pending = deferred<{ job_id: string; state: 'queued' }>(); vi.mocked(jobApi.exportOnnx).mockReturnValueOnce(pending.promise)
  const first = create(); await flushPromises(); await first.find('select').setValue('pt-a'); await flushPromises(); await first.find('form').trigger('submit')
  first.unmount()
  const second = create(); await flushPromises(); await second.find('select').setValue('pt-a'); await flushPromises(); await second.find('form').trigger('submit'); await flushPromises()
  const calls = vi.mocked(jobApi.exportOnnx).mock.calls; expect(calls).toHaveLength(2); expect(calls[0][2]).toBe(calls[1][2]); expect(calls[0][3]?.aborted).toBe(true)
  pending.resolve({ job_id: 'obsolete', state: 'queued' }); await flushPromises(); expect(second.text()).not.toContain('obsolete')
})
it('rotates the key only for an explicit new retry of a failed export', async () => {
  mocks()
  const failed: Job = { ...job('export-a', 'failed'), export: { source_artifact_id: 'pt-a', source_job_id: 'train-a', source_sha256: sha, params: { model_artifact_id: 'pt-a', batch: 1, imgsz: 640, precision: 'fp32' }, runtime_binding: sha, code_version: sha } }
  const priorKey = crypto.randomUUID(); sessionStorage.setItem('edgevision.export.v1:p:pt-a', priorKey)
  vi.mocked(jobApi.detail).mockImplementation(async id => id.startsWith('train') ? job(id, 'succeeded', 'p', 'train') : id === 'export-a' ? failed : job(id))
  const wrapper = create(); await flushPromises(); await button(wrapper, '重新导出（新任务）').trigger('click'); await flushPromises()
  expect(jobApi.exportOnnx).toHaveBeenCalledTimes(1); expect(vi.mocked(jobApi.exportOnnx).mock.calls[0][2]).not.toBe(priorKey)
  await wrapper.find('form').trigger('submit'); expect(jobApi.exportOnnx).toHaveBeenCalledTimes(1)
})

it.each(['lost-post', 'failed-detail'])('reuses the failed-job replacement key after %s and remount', async mode => {
  mocks()
  const failed: Job = { ...job('export-a', 'failed'), export: { source_artifact_id: 'pt-a', source_job_id: 'train-a', source_sha256: sha, params: { model_artifact_id: 'pt-a', batch: 1, imgsz: 640, precision: 'fp32' }, runtime_binding: sha, code_version: sha } }
  vi.mocked(jobApi.detail).mockImplementation(async id => {
    if (id.startsWith('train')) return job(id, 'succeeded', 'p', 'train')
    if (id === 'export-a') return failed
    throw new Error('detail unavailable')
  })
  if (mode === 'lost-post') vi.mocked(jobApi.exportOnnx).mockRejectedValueOnce(new Error('response lost'))
  const first = create(); await flushPromises()
  await button(first, '重新导出（新任务）').trigger('click'); await flushPromises()
  await button(first, '重新导出（新任务）').trigger('click'); await flushPromises()
  first.unmount()
  const second = create(); await flushPromises()
  await button(second, '重新导出（新任务）').trigger('click'); await flushPromises()
  const calls = vi.mocked(jobApi.exportOnnx).mock.calls
  expect(calls).toHaveLength(3)
  expect(new Set(calls.map(call => call[2])).size).toBe(1)
  expect(second.text()).toContain('已接收任务 new-export')
  await second.find('form').trigger('submit'); expect(jobApi.exportOnnx).toHaveBeenCalledTimes(3)
})
