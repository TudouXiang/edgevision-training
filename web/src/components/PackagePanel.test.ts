// @vitest-environment happy-dom
// Synthetic API fixtures only, never native execution evidence.
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import PackagePanel from './PackagePanel.vue'
import { jobApi } from '../api'
import type { Artifact, Job, Project } from '../api'
const date = '2026-11-04T00:00:00Z', sha = 'a'.repeat(64)
const project: Project = { id: 'p', owner_id: 'u', name: 'P', description: '', archived_at: null, created_at: date, updated_at: date }
const capability = { available: true, reason: null, reason_code: null, detected_version: '1.31.1' }
const job = (id = 'package-a', state: Job['state'] = 'running', project_id = 'p', kind: Job['kind'] = 'package'): Job => ({ id, project_id, created_by: 'u', kind, state, params_schema_version: 1, created_at: date, started_at: date, finished_at: null, error_code: null, source_job_id: null, ...(kind === 'package' ? { package: { onnx_artifact_id: 'onnx-a', export_job_id: 'export-a', source_sha256: sha, template_sha256: sha, params: { onnx_artifact_id: 'onnx-a' }, runtime_binding: sha, code_version: sha } } : {}) })
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

const page=<T,>(items:T[])=>({items,total:items.length,page:1,page_size:100})
const wrappers:ReturnType<typeof mount>[]=[]
function create(extra={}) {const wrapper=mount(PackagePanel,{props:{userId:'u',project,capability,...extra}});wrappers.push(wrapper);return wrapper}
function button(w:ReturnType<typeof mount>,text:string){return w.findAll('button').find(b=>b.text()===text)!}
function mocks(){
 vi.useFakeTimers()
 vi.spyOn(jobApi,'list').mockResolvedValue(page([job()]))
 vi.spyOn(jobApi,'detail').mockImplementation(async id=>id==='export-a'?job(id,'succeeded','p','export_onnx'):job(id))
 vi.spyOn(jobApi,'artifacts').mockResolvedValue(page([onnx()]))
 vi.spyOn(jobApi,'logs').mockResolvedValue({items:[],next_cursor:null,eof:false,job_state:'running'})
 vi.spyOn(jobApi,'package').mockResolvedValue({job_id:'new-package',state:'queued'})
 vi.spyOn(jobApi,'cancel').mockImplementation(async id=>job(id,'cancelled'))
}
afterEach(()=>{wrappers.splice(0).forEach(w=>w.unmount());vi.restoreAllMocks();vi.useRealTimers();sessionStorage.clear()})
async function select(w:ReturnType<typeof mount>){await flushPromises();await w.find('select').setValue('onnx-a');await flushPromises()}
it('keeps unavailable deployment disabled and states dependency limits',async()=>{
 mocks();const w=create({capability:{...capability,available:false,reason:'未验证'}});await select(w);await w.find('form').trigger('submit')
 expect(jobApi.package).not.toHaveBeenCalled();expect(w.text()).toContain('未验证');expect(w.text()).toContain('不包含 Python');expect(w.text()).toContain('联网')
})
it('accepts only passed same-project ONNX from succeeded export jobs',async()=>{
 mocks();vi.mocked(jobApi.artifacts).mockResolvedValue(page([onnx(),pt(),{...onnx(),id:'foreign',project_id:'elsewhere'},{...onnx(),id:'failed-source',job_id:'bad'}]))
 const w=create();await flushPromises();expect(w.findAll('option').map(x=>x.attributes('value'))).toEqual(['','onnx-a'])
})
it('submits exact source once and blocks accepted requests across remount',async()=>{
 mocks();const first=create();await select(first);await first.find('form').trigger('submit');await first.find('form').trigger('submit');await flushPromises()
 expect(jobApi.package).toHaveBeenCalledTimes(1);expect(vi.mocked(jobApi.package).mock.calls[0][1]).toEqual({onnx_artifact_id:'onnx-a'});expect(first.find('h3').text()).toContain('running');expect(first.find('.identity').text()).toBe('new-package');expect(first.find('[role=alert]').exists()).toBe(false)
 first.unmount();const second=create();await select(second);await second.find('form').trigger('submit');expect(jobApi.package).toHaveBeenCalledTimes(1)
})
it('reuses request identity after a lost response and reload',async()=>{
 mocks();vi.mocked(jobApi.package).mockRejectedValueOnce(new Error('lost'))
 const first=create();await select(first);await first.find('form').trigger('submit');await flushPromises();first.unmount()
 const second=create();await select(second);await second.find('form').trigger('submit');await flushPromises()
 expect(jobApi.package).toHaveBeenCalledTimes(2);const calls=vi.mocked(jobApi.package).mock.calls;expect(calls[0][2]).toBe(calls[1][2])
})
it('keeps retry source and key after response loss and reload',async()=>{
 mocks();const failed={...job('package-a','failed'),package:{onnx_artifact_id:'onnx-a',export_job_id:'export-a',source_sha256:sha,template_sha256:sha,params:{onnx_artifact_id:'onnx-a'},runtime_binding:sha,code_version:sha}}
 vi.mocked(jobApi.detail).mockImplementation(async id=>id==='export-a'?job(id,'succeeded','p','export_onnx'):failed)
 vi.mocked(jobApi.package).mockRejectedValue(new Error('lost'))
 const first=create();await flushPromises();await button(first,'重新打包（新任务）').trigger('click');await flushPromises();first.unmount()
 const second=create();await flushPromises();await button(second,'重新打包（新任务）').trigger('click');await flushPromises()
 const calls=vi.mocked(jobApi.package).mock.calls;expect(calls).toHaveLength(2);expect(calls[0][4]).toBe('package-a');expect(calls[1][4]).toBe('package-a');expect(calls[0][2]).toBe(calls[1][2])
})
it('partitions saved requests by authenticated user',async()=>{
 mocks();const first=create();await select(first);await first.find('form').trigger('submit');await flushPromises();first.unmount()
 const second=create({userId:'other-user'});await select(second);await second.find('form').trigger('submit');await flushPromises()
 const calls=vi.mocked(jobApi.package).mock.calls;expect(calls).toHaveLength(2);expect(calls[0][2]).not.toBe(calls[1][2])
})
it('keeps polling after changing model and cancels through existing API',async()=>{
 mocks();const w=create();await select(w);await vi.advanceTimersByTimeAsync(2000);await flushPromises();expect(jobApi.list).toHaveBeenCalledTimes(3)
 await button(w,'package-a · running').trigger('click');await flushPromises();await button(w,'取消打包').trigger('click');await flushPromises();expect(jobApi.cancel).toHaveBeenCalledWith('package-a',expect.anything())
})
it('aborts old account requests and ignores late inventory',async()=>{
 mocks();let resolve!:(v:ReturnType<typeof page<Artifact>>)=>void
 const pending=new Promise<ReturnType<typeof page<Artifact>>>(r=>{resolve=r});vi.mocked(jobApi.artifacts).mockReturnValueOnce(pending)
 const w=create();await flushPromises();const old=vi.mocked(jobApi.artifacts).mock.calls[0][1]!
 vi.mocked(jobApi.artifacts).mockResolvedValue(page([]));vi.mocked(jobApi.list).mockResolvedValue(page([]));await w.setProps({userId:'other-user'});await flushPromises();resolve(page([onnx()]));await flushPromises()
 expect(old.aborted).toBe(true);expect(w.findAll('option')).toHaveLength(1)
})

function packageArtifact(): Extract<Artifact,{kind:'deployment_zip'}> {
 return {id:'package-zip',project_id:'p',job_id:'package-a',kind:'deployment_zip',format:'zip',sha256:sha,size_bytes:100,
  metadata_schema_version:1,validation_state:'passed',created_at:date,
  metadata:{schema_version:1,protocol:'edgevision-python-onnx-v1',validation_scope:'trusted_model_fixed_package_integrity',standalone_execution:'not_run_for_this_artifact',
   package_sha256:sha,package_size_bytes:100,manifest_sha256:sha,manifest_size_bytes:50,template_validation_sha256:sha,
   template:{protocol:'edgevision-python-onnx-v1',image_protocol:'detection-image-v1',target:'linux-x86_64-cpython312-cpu',template_sha256:sha,core_sha256:sha,lock_sha256:sha},
   provenance:{job_id:'package-a',run_id:'run',project_id:'p',onnx_artifact_id:'onnx-a',export_job_id:'export-a',parent_artifact_id:'pt-a',frozen_input_sha256:sha,model_sha256:sha,model_size_bytes:200,model_metadata_sha256:sha,runtime_binding:sha,code_version:sha}}}
}
it('only offers the selected successful package download and honest scope',async()=>{
 mocks();vi.mocked(jobApi.detail).mockImplementation(async id=>id==='export-a'?job(id,'succeeded','p','export_onnx'):job(id,'succeeded'))
 vi.mocked(jobApi.artifacts).mockResolvedValue(page([onnx(),packageArtifact(),{...packageArtifact(),id:'foreign',project_id:'elsewhere'},{...packageArtifact(),id:'other-job',job_id:'elsewhere'}]))
 const w=create();await flushPromises();expect(w.findAll('a')).toHaveLength(1)
 expect(w.find('a').attributes('href')).toBe('/api/v1/artifacts/package-zip/download');expect(w.text()).toContain('不会逐包执行模型')
})
it('does not show a package download while the job has failed',async()=>{
 mocks();vi.mocked(jobApi.detail).mockImplementation(async id=>id==='export-a'?job(id,'succeeded','p','export_onnx'):job(id,'failed'))
 vi.mocked(jobApi.artifacts).mockResolvedValue(page([onnx(),packageArtifact()]))
 const w=create();await flushPromises();expect(w.findAll('a')).toHaveLength(0)
})

it('ignores an accepted POST response after account scope changes',async()=>{
 mocks();let resolve!:(v:{job_id:string;state:'queued'})=>void
 const pending=new Promise<{job_id:string;state:'queued'}>(r=>{resolve=r});vi.mocked(jobApi.package).mockReturnValueOnce(pending)
 const w=create();await select(w);await w.find('form').trigger('submit')
 await w.setProps({userId:'other-user'});await flushPromises();resolve({job_id:'obsolete',state:'queued'});await flushPromises()
 expect(w.text()).not.toContain('obsolete');expect(jobApi.detail).not.toHaveBeenCalledWith('obsolete',expect.anything())
 expect(sessionStorage.getItem('edgevision.package.v1:other-user:p:onnx-a')).toBeNull()
})
it('rejects a mismatched task detail instead of showing its output',async()=>{
 mocks();vi.mocked(jobApi.detail).mockImplementation(async id=>id==='export-a'?job(id,'succeeded','p','export_onnx'):job('wrong-id','succeeded'))
 vi.mocked(jobApi.artifacts).mockResolvedValue(page([onnx(),packageArtifact()]))
 const w=create();await flushPromises();expect(w.findAll('a')).toHaveLength(0);expect(w.find('[role=alert]').exists()).toBe(true)
})
