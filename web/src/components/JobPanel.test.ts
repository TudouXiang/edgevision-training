// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import JobPanel from './JobPanel.vue'
import { datasetApi, jobApi } from '../api'
import type { Dataset, Job } from '../api'

const job: Job = { id: '00000000-0000-4000-8000-000000000001', project_id: '00000000-0000-4000-8000-000000000002', created_by: '00000000-0000-4000-8000-000000000003', kind: 'dataset_check', state: 'running', params_schema_version: 1, created_at: '2026-11-04T00:00:00Z', started_at: '2026-11-04T00:00:01Z', finished_at: null, error_code: null, source_job_id: null }
const dataset: Dataset = { id: '00000000-0000-4000-8000-000000000004', project_id: job.project_id, name: 'tiny', version: 1, state: 'pending', sha256: '0'.repeat(64), size_bytes: 1, classes: [], counts: null, created_at: job.created_at, validation_job_id: null, report_artifact_id: null }
const page = (items: Job[]) => ({ items, total: items.length, page: 1, page_size: 20 })
const mounted: ReturnType<typeof mount>[] = []
function create() { const wrapper = mount(JobPanel, { props: { projectId: job.project_id, datasets: [dataset] } }); mounted.push(wrapper); return wrapper }
afterEach(() => { mounted.splice(0).forEach(wrapper => wrapper.unmount()); vi.restoreAllMocks(); vi.useRealTimers() })

function mocks() {
  vi.spyOn(jobApi, 'list').mockResolvedValue(page([{ ...job }]))
  vi.spyOn(datasetApi, 'detail').mockResolvedValue({ ...dataset, state: 'validating', validation_job_id: job.id })
  vi.spyOn(jobApi, 'logs').mockResolvedValue({ items: [], next_cursor: 'cursor', eof: false, job_state: 'running' })
}

describe('real-state job polling UI', () => {
  it('reads final terminal logs and keeps Close closed on the next poll', async () => {
    vi.useFakeTimers()
    mocks()
    vi.mocked(jobApi.logs).mockResolvedValueOnce({ items: [{ seq: 2, at: job.created_at, level: 'info', text: 'started' }], next_cursor: 'c2', eof: false, job_state: 'running' })
    const wrapper = create()
    await flushPromises()
    expect(wrapper.text()).toContain('started')
    vi.mocked(jobApi.list).mockResolvedValue(page([{ ...job, state: 'succeeded' }]))
    vi.mocked(jobApi.logs).mockResolvedValue({ items: [{ seq: 3, at: job.created_at, level: 'info', text: 'finished' }], next_cursor: 'c4', eof: true, job_state: 'succeeded' })
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(wrapper.text()).toContain('finished')
    expect(wrapper.text()).toContain('已读取最终日志')
    await wrapper.findAll('button').find(button => button.text() === '关闭日志')!.trigger('click')
    await vi.advanceTimersByTimeAsync(2000)
    expect(wrapper.find('[aria-label="任务日志"]').exists()).toBe(false)
  })

  it('deduplicates repeated submit and reuses its key after an uncertain response', async () => {
    vi.useFakeTimers()
    mocks()
    let reject!: (reason: unknown) => void
    const uncertain = new Promise<never>((_, fail) => { reject = fail })
    const check = vi.spyOn(datasetApi, 'check').mockReturnValueOnce(uncertain).mockResolvedValue({ job_id: job.id, state: 'queued' })
    const wrapper = create()
    await flushPromises()
    const first = wrapper.vm.checkDataset(dataset)
    const repeated = wrapper.vm.checkDataset(dataset)
    expect(check).toHaveBeenCalledTimes(1)
    reject(new Error('connection lost'))
    await Promise.all([first, repeated])
    await wrapper.vm.checkDataset(dataset)
    expect(check).toHaveBeenCalledTimes(2)
    expect(check.mock.calls[0][1]).toBe(check.mock.calls[1][1])
  })

  it('aborts pending reads on unmount and ignores a late result', async () => {
    vi.useFakeTimers()
    mocks()
    let resolve!: (value: Awaited<ReturnType<typeof jobApi.logs>>) => void
    vi.mocked(jobApi.logs).mockReturnValue(new Promise(done => { resolve = done }))
    const wrapper = create()
    await flushPromises()
    const signal = vi.mocked(jobApi.logs).mock.calls[0][2]!
    wrapper.unmount()
    expect(signal.aborted).toBe(true)
    resolve({ items: [], next_cursor: 'late', eof: true, job_state: 'succeeded' })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(jobApi.list).toHaveBeenCalledTimes(1)
  })
})

it('offers historical task pages and submits new work on page one', async () => {
  vi.useFakeTimers()
  mocks()
  vi.mocked(jobApi.list).mockResolvedValue({ ...page([{ ...job }]), total: 21 })
  vi.spyOn(datasetApi, 'check').mockResolvedValue({ job_id: job.id, state: 'queued' })
  const wrapper = create()
  await flushPromises()
  await wrapper.findAll('button').find(button => button.text() === '下一页任务')!.trigger('click')
  await flushPromises()
  expect(vi.mocked(jobApi.list).mock.calls.at(-1)?.[2]).toBe(2)
  expect(wrapper.text()).toContain('第 2 / 2 页')
  await wrapper.vm.checkDataset(dataset)
  expect(vi.mocked(jobApi.list).mock.calls.at(-1)?.[2]).toBe(1)
})
