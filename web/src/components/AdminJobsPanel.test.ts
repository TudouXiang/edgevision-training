// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import AdminJobsPanel from './AdminJobsPanel.vue'
import { adminApi, jobApi } from '../api'
import type { Job } from '../api'
const job: Job = { id:'00000000-0000-4000-8000-000000000001', project_id:'00000000-0000-4000-8000-000000000002', created_by:'00000000-0000-4000-8000-000000000003', kind:'dataset_check', state:'running', params_schema_version:1, created_at:'2026-11-14T00:00:00Z', started_at:null, finished_at:null, error_code:null, source_job_id:null }
const page = (items = [job], current = 1, total = items.length) => ({ items, total, page:current, page_size:20 })
const mounted: ReturnType<typeof mount>[] = []
function create() { const w = mount(AdminJobsPanel); mounted.push(w); return w }
function setup() {
 vi.spyOn(adminApi, 'jobs').mockResolvedValue(page())
 vi.spyOn(jobApi, 'detail').mockResolvedValue({...job})
 vi.spyOn(jobApi, 'logs').mockResolvedValue({items:[], next_cursor:null, eof:true, job_state:'running'})
}
const button = (w: ReturnType<typeof mount>, text: string) => w.findAll('button').find(x=>x.text()===text)!
function deferred<T>() { let resolve!: (v:T)=>void; const promise = new Promise<T>(done=>{resolve=done}); return {promise,resolve} }
afterEach(()=>{ mounted.splice(0).forEach(w=>w.unmount()); vi.restoreAllMocks() })

it('shows real tasks, bounded pages and explicit offline recovery', async()=>{
 setup(); vi.mocked(adminApi.jobs).mockResolvedValueOnce(page([job],1,21))
 const w=create(); await flushPromises(); expect(w.text()).toContain(job.project_id)
 await button(w,'下一页').trigger('click'); await flushPromises()
 expect(adminApi.jobs).toHaveBeenLastCalledWith(2,20,expect.any(AbortSignal))
 vi.mocked(adminApi.jobs).mockRejectedValueOnce(new Error('offline'))
 await button(w,'刷新任务').trigger('click'); await flushPromises()
 expect(w.find('[role="alert"]').text()).toContain('尚未刷新')
 await button(w,'刷新任务').trigger('click'); await flushPromises()
 expect(w.find('[role="alert"]').exists()).toBe(false)
})
it('ignores stale selection details and unmount aborts pending reads',async()=>{
 setup(); const second={...job,id:'00000000-0000-4000-8000-000000000004'}
 vi.mocked(adminApi.jobs).mockResolvedValue(page([job,second]))
 const first=deferred<Job>(); vi.mocked(jobApi.detail).mockReturnValueOnce(first.promise).mockResolvedValueOnce({...second,error_code:'SECOND'})
 const w=create(); await flushPromises(); await w.findAll('[data-detail]')[0]!.trigger('click'); await w.findAll('[data-detail]')[1]!.trigger('click'); await flushPromises()
 first.resolve({...job,error_code:'STALE'}); await flushPromises()
 expect(w.text()).toContain('SECOND'); expect(w.text()).not.toContain('STALE')
 const signal=vi.mocked(adminApi.jobs).mock.calls[0]![2]!
 w.unmount(); expect(signal.aborted).toBe(true)
})
it('deduplicates cancellation and never claims cancelling means stopped',async()=>{
 setup(); const pending=deferred<Job>(); const cancel=vi.spyOn(jobApi,'cancel').mockReturnValue(pending.promise)
 const w=create(); await flushPromises(); await button(w,'查看').trigger('click'); await flushPromises()
 const b=button(w,'请求取消'); b.element.click(); b.element.click(); await flushPromises(); expect(cancel).toHaveBeenCalledTimes(1)
 pending.resolve({...job,state:'cancelling'}); await flushPromises()
 expect(w.text()).toContain('等待'); expect(w.text()).toContain('cancelling'); expect(w.text()).not.toContain('任务已停止')
})
it('reports cancellation failures and allows retry',async()=>{
 setup(); const cancel=vi.spyOn(jobApi,'cancel').mockRejectedValueOnce(new Error('offline')).mockResolvedValue({...job,state:'cancelled'})
 const w=create(); await flushPromises(); await button(w,'查看').trigger('click'); await flushPromises(); await button(w,'请求取消').trigger('click'); await flushPromises()
 expect(w.find('[role="alert"]').exists()).toBe(true)
 await button(w,'请求取消').trigger('click'); await flushPromises(); expect(cancel).toHaveBeenCalledTimes(2); expect(w.text()).toContain('cancelled')
})

it('ignores a cancelled task response after switching to another task',async()=>{
 setup(); const second={...job,id:'00000000-0000-4000-8000-000000000004'}
 vi.mocked(adminApi.jobs).mockResolvedValue(page([job,second]))
 vi.mocked(jobApi.detail).mockResolvedValueOnce(job).mockResolvedValueOnce(second)
 const pending=deferred<Job>(); vi.spyOn(jobApi,'cancel').mockReturnValue(pending.promise)
 const w=create(); await flushPromises(); await w.findAll('[data-detail]')[0]!.trigger('click'); await flushPromises()
 await button(w,'请求取消').trigger('click'); await w.findAll('[data-detail]')[1]!.trigger('click'); await flushPromises()
 pending.resolve({...job,state:'cancelled'}); await flushPromises()
 expect(w.find('[aria-label="全局任务详情"]').text()).toContain(second.id)
 expect(w.find('[aria-label="全局任务详情"]').text()).not.toContain('cancelled')
})
it('bounds retained logs to the last 500 and ignores resolved reads after unmount',async()=>{
 setup()
 let seq=0
 vi.mocked(jobApi.logs).mockImplementation(async()=>({items:Array.from({length:100},()=>({seq:++seq,at:job.created_at,level:'info' as const,text:`line-${seq}`})),next_cursor:String(seq),eof:false,job_state:'running'}))
 const w=create(); await flushPromises(); await button(w,'查看').trigger('click'); await flushPromises()
 for(let i=0;i<5;i++){await button(w,'读取后续日志').trigger('click'); await flushPromises()}
 const log=w.find('pre').text().split('\n'); expect(log).toHaveLength(500);expect(log[0]).toBe('line-101');expect(log.at(-1)).toBe('line-600')
 const pending=deferred<Awaited<ReturnType<typeof adminApi.jobs>>>()
 vi.mocked(adminApi.jobs).mockReturnValue(pending.promise)
 await button(w,'刷新任务').trigger('click'); w.unmount()
 pending.resolve(page([{...job,error_code:'AFTER_UNMOUNT'}])); await flushPromises()
 expect(w.emitted('error')).toBeUndefined()
})
