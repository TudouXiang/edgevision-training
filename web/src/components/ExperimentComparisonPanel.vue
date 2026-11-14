<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ApiClientError, jobApi } from '../api'
import type { Job, Metric, Project } from '../api'
const props=defineProps<{project:Project}>()
const emit=defineEmits<{error:[value:unknown]}>()
const list=ref<Job[]>([]), retained=ref<Job[]>([]), page=ref(1), total=ref(0), listing=ref(false)
const left=ref(''),right=ref(''),loading=ref(false),warning=ref('')
type Result={job:Job; metrics:Record<string,Metric>}
const results=ref<Result[]|null>(null)
const lifetime=new AbortController()
let run:AbortController|undefined,revision=0,listRevision=0
const choices=computed(()=>[...new Map([...retained.value,...list.value].map(j=>[j.id,j])).values()])
const names=computed(()=>[...new Set(results.value?.flatMap(r=>Object.keys(r.metrics))??[])].sort())
const differs=computed(()=>{
 const a=results.value?.[0]?.job.training,b=results.value?.[1]?.job.training
 return !!a&&!!b&&(['dataset_id','dataset_version','snapshot_sha256','base_model_sha256','base_manifest_sha256','runtime_binding','code_version'] as const).some(k=>a[k]!==b[k])
})
function report(e:unknown,message:string){if(lifetime.signal.aborted||e instanceof DOMException&&e.name==='AbortError')return;warning.value=message;if(e instanceof ApiClientError&&e.status===401)emit('error',e)}
function invalidate(){revision++;run?.abort();results.value=null;loading.value=false;warning.value='';retained.value=choices.value.filter(j=>j.id===left.value||j.id===right.value)}
watch([left,right],invalidate,{flush:'sync'})
async function refresh(target=page.value){
 const expected=++listRevision;listing.value=true
 try{const response=await jobApi.list(props.project.id,lifetime.signal,target);if(lifetime.signal.aborted||expected!==listRevision)return
  retained.value=choices.value.filter(j=>j.id===left.value||j.id===right.value)
  list.value=response.items.filter(j=>j.kind==='train'&&j.state==='succeeded'&&j.project_id===props.project.id)
  page.value=response.page;total.value=response.total;warning.value=''
 }catch(e){if(expected===listRevision)report(e,'实验列表尚未刷新，请重试。')}
 finally{if(!lifetime.signal.aborted&&expected===listRevision)listing.value=false}
}
async function read(id:string,signal:AbortSignal):Promise<Result>{
 const task=await jobApi.detail(id,signal)
 if(signal.aborted)throw new DOMException('Aborted','AbortError')
 if(task.id!==id||task.project_id!==props.project.id||task.kind!=='train'||task.state!=='succeeded'||!task.training)throw new Error('任务不符合最终比较条件。')
 let cursor:string|null=null,last=0;const values:Record<string,Metric>={};const cursors=new Set<string>()
 for(let i=0;i<4;i++){
  const response=await jobApi.metrics(id,cursor,signal)
  if(signal.aborted)throw new DOMException('Aborted','AbortError')
  if(response.job_state!=='succeeded'||response.items.length>500)throw new Error('指标读取不完整。')
  for(const m of response.items){
   if(!Number.isFinite(m.value)||!Number.isSafeInteger(m.seq)||m.seq<=last||!Number.isSafeInteger(m.epoch)||m.epoch<1)throw new Error('指标读取不完整。')
   last=m.seq;const previous=values[m.name]
   if(!previous||m.epoch>previous.epoch||m.epoch===previous.epoch&&m.seq>previous.seq)values[m.name]=m
  }
  if(response.eof)return {job:task,metrics:values}
  if(!response.next_cursor||response.next_cursor===cursor||cursors.has(response.next_cursor))throw new Error('指标读取不完整。')
  cursor=response.next_cursor;cursors.add(cursor)
 }
 throw new Error('指标读取不完整：已达到单任务 2000 项读取上限。')
}
async function compare(){
 if(!left.value||!right.value||left.value===right.value||loading.value)return
 run?.abort();run=new AbortController();const controller=run,expected=++revision,ids=[left.value,right.value]
 loading.value=true;results.value=null;warning.value=''
 try{const values:Result[]=[];for(const id of ids)values.push(await read(id,controller.signal))
  if(!lifetime.signal.aborted&&!controller.signal.aborted&&expected===revision)results.value=values
 }catch(e){if(expected===revision&&!controller.signal.aborted)report(e,e instanceof ApiClientError?'实验读取失败，请重试。':e instanceof Error?e.message:'实验读取失败，请重试。')}
 finally{if(!lifetime.signal.aborted&&expected===revision)loading.value=false}
}
const provenance=[['dataset_id','数据集'],['dataset_version','数据版本'],['snapshot_sha256','数据快照摘要'],['base_model_sha256','基础权重摘要'],['base_manifest_sha256','基础权重清单'],['runtime_binding','运行环境'],['code_version','代码版本']] as const
const parameters=[['imgsz','图像尺寸'],['epochs','训练轮数'],['seed','随机种子'],['batch','批量大小'],['learning_rate','学习率']] as const
onMounted(()=>void refresh())
onUnmounted(()=>{lifetime.abort();run?.abort();revision++;listRevision++})
</script>
<template>
 <section class="panel experiment-comparison" aria-label="基础实验对比">
  <h2>基础实验对比</h2><p class="note">选择同项目两个成功训练任务。展示训练记录的最后观测指标，不是独立测试集报告；不自动判定优劣。</p>
  <p v-if="warning" role="alert">{{ warning }}</p>
  <div class="actions"><button :disabled="listing" @click="refresh()">刷新实验</button><button :disabled="listing||page<=1" @click="refresh(page-1)">上一页实验</button><span>任务第 {{ page }} 页</span><button :disabled="listing||page*20>=total" @click="refresh(page+1)">下一页实验</button></div>
  <p v-if="!listing&&!list.length" class="note">当前任务页没有成功训练，可切换任务页。没有模拟实验。</p>
  <div class="grid-form"><label>实验 A<select v-model="left" aria-label="实验 A"><option value="">选择实验</option><option v-for="j in choices" :key="j.id" :value="j.id">{{ j.training?.params.experiment_name??j.id }} · {{ j.id }}</option></select></label><label>实验 B<select v-model="right" aria-label="实验 B"><option value="">选择实验</option><option v-for="j in choices" :key="j.id" :value="j.id">{{ j.training?.params.experiment_name??j.id }} · {{ j.id }}</option></select></label><button :disabled="loading||!left||!right||left===right" @click="compare">对比所选实验</button></div>
  <p v-if="loading" role="status">正在读取完整指标…</p>
  <section v-if="results" data-results aria-label="实验对比结果">
   <p v-if="differs" role="status">数据来源、基础权重、环境或代码不同，不宜直接排名。请先确认实验口径。</p>
   <p class="note">即使来源相同，也应核对下方训练参数。缺失指标显示“未提供”，不当作 0。</p>
   <div class="comparison-grid"><article v-for="r in results" :key="r.job.id">
    <h3>{{ r.job.training!.params.experiment_name }}</h3><p>{{ r.job.id }} · succeeded</p>
    <dl><template v-for="[key,label] in provenance" :key="key"><dt>{{ label }}</dt><dd>{{ r.job.training![key] }}</dd></template><template v-for="[key,label] in parameters" :key="key"><dt>{{ label }}</dt><dd>{{ r.job.training!.params[key]??'未提供' }}</dd></template></dl>
    <h4>最终已读取指标</h4><p v-if="!names.length">两次任务均未提供指标。</p>
    <dl><template v-for="name in names" :key="name"><dt>{{ name }}</dt><dd>{{ r.metrics[name] ? `${r.metrics[name]!.value.toPrecision(6)}（第 ${r.metrics[name]!.epoch} 轮）` : '未提供' }}</dd></template></dl>
   </article></div>
  </section>
 </section>
</template>
<style scoped>
.comparison-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:16px}.comparison-grid article{min-width:0;background:#f3f6fa;padding:12px;border-radius:12px}.comparison-grid dd{margin:0 0 8px;overflow-wrap:anywhere}.comparison-grid p{overflow-wrap:anywhere}.experiment-comparison select{max-width:100%}
</style>
