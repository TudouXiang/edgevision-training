// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import TrainingPanel from './TrainingPanel.vue'
import { jobApi } from '../api'
import type { Dataset, Job, Project } from '../api'
const date='2026-11-04T00:00:00Z'
const project:Project={id:'p',owner_id:'u',name:'P',description:'',archived_at:null,created_at:date,updated_at:date}
const dataset:Dataset={id:'d',project_id:'p',name:'D',version:1,state:'ready',sha256:'a'.repeat(64),size_bytes:10,classes:['object'],counts:{images:8},created_at:date}
const job=(id='a'):Job=>({id,project_id:'p',created_by:'u',kind:'train',state:'running',params_schema_version:1,created_at:date,started_at:date,finished_at:null,error_code:null,source_job_id:null})
const mounted:ReturnType<typeof mount>[]=[]
function create(){const wrapper=mount(TrainingPanel,{props:{project,datasets:[dataset],capability:{available:true,reason:null,reason_code:null,detected_version:'8.4.202'}}});mounted.push(wrapper);return wrapper}
function mocks(){
 vi.useFakeTimers()
 vi.spyOn(jobApi,'list').mockResolvedValue({items:[job('a'),job('b')],total:2,page:1,page_size:20})
 vi.spyOn(jobApi,'detail').mockImplementation(async id=>job(id))
 vi.spyOn(jobApi,'metrics').mockResolvedValue({items:[],next_cursor:null,eof:false,job_state:'running'})
 vi.spyOn(jobApi,'artifacts').mockResolvedValue({items:[],total:0,page:1,page_size:100})
}
afterEach(()=>{mounted.splice(0).forEach(w=>w.unmount());vi.restoreAllMocks();vi.useRealTimers()})
it('ignores cancellation response after another job is selected',async()=>{
 mocks();let resolve!:(j:Job)=>void
 vi.spyOn(jobApi,'cancel').mockReturnValue(new Promise(done=>resolve=done))
 const wrapper=create();await flushPromises()
 await wrapper.findAll('button').find(b=>b.text()==='取消训练')!.trigger('click')
 await wrapper.findAll('button').find(b=>b.text()==='b · running')!.trigger('click');await flushPromises()
 resolve({...job('a'),state:'cancelled'});await flushPromises()
 expect(wrapper.find('h3').text()).toContain('running')
 await vi.advanceTimersByTimeAsync(2000);await flushPromises()
 expect(vi.mocked(jobApi.detail).mock.calls.at(-1)?.[0]).toBe('b')
})
it('retains submission key after accepted response but failed detail',async()=>{
 mocks();vi.mocked(jobApi.list).mockResolvedValue({items:[],total:0,page:1,page_size:20})
 const train=vi.spyOn(jobApi,'train').mockResolvedValue({job_id:'accepted',state:'queued'})
 vi.mocked(jobApi.detail).mockRejectedValueOnce(new Error('detail unavailable')).mockResolvedValue(job('accepted'))
 const wrapper=create();await flushPromises();await wrapper.find('select').setValue('d')
 await wrapper.find('form').trigger('submit');await flushPromises()
 await wrapper.find('form').trigger('submit');await flushPromises()
 expect(train).toHaveBeenCalledTimes(2);expect(train.mock.calls[0][2]).toBe(train.mock.calls[1][2])
})
it('backs off errors while terminal metrics are still draining',async()=>{
 mocks();vi.mocked(jobApi.detail).mockResolvedValue({...job(),state:'succeeded'})
 vi.mocked(jobApi.metrics).mockRejectedValue(new Error('offline'))
 const wrapper=create();await flushPromises();expect(wrapper.text()).toContain('offline')
 await vi.advanceTimersByTimeAsync(3000);expect(jobApi.metrics).toHaveBeenCalledTimes(1)
 await vi.advanceTimersByTimeAsync(1000);await flushPromises();expect(jobApi.metrics).toHaveBeenCalledTimes(2)
})
it('aborts reads when project/session panel unmounts',async()=>{
 mocks();let resolve!:(value:Awaited<ReturnType<typeof jobApi.metrics>>)=>void
 vi.mocked(jobApi.metrics).mockReturnValue(new Promise(done=>resolve=done))
 const wrapper=create();await flushPromises();const signal=vi.mocked(jobApi.metrics).mock.calls[0][2]!
 wrapper.unmount();expect(signal.aborted).toBe(true);resolve({items:[],next_cursor:null,eof:true,job_state:'succeeded'});await flushPromises()
 await vi.advanceTimersByTimeAsync(10000);expect(jobApi.list).toHaveBeenCalledTimes(1)
})
it('reads final metrics and renders no fabricated value',async()=>{
 mocks();vi.mocked(jobApi.detail).mockResolvedValue({...job(),state:'succeeded'})
 vi.mocked(jobApi.metrics).mockResolvedValue({items:[{seq:1,epoch:1,name:'train/box_loss',value:.75,at:date}],next_cursor:'c',eof:true,job_state:'succeeded'})
 const wrapper=create();await flushPromises();expect(wrapper.text()).toContain('最终指标已读取');expect(wrapper.text()).toContain('0.75000')
 await vi.advanceTimersByTimeAsync(2000);expect(jobApi.metrics).toHaveBeenCalledTimes(1)
})
