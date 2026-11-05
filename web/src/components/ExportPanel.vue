<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { ApiClientError, jobApi } from '../api'
import type { Artifact, Capabilities, ExportOnnxParams, Job, JobLog, Project } from '../api'

const props = defineProps<{ project: Project; capability?: Capabilities['features'][string] }>()
const emit = defineEmits<{ error: [value: unknown] }>()
const models = ref<Artifact[]>([]), modelId = ref(''), jobs = ref<Job[]>([]), selected = ref<Job | null>(null)
const outputs = ref<Extract<Artifact, { kind: 'onnx' }>[]>([]), lines = ref<JobLog[]>([]), logDone = ref(false)
const warning = ref(''), actionWarning = ref(''), storageWarning = ref(''), loading = ref(false), submitting = ref(false), cancelling = ref(false)
const page = ref(1), total = ref(0), acceptedModels = ref<Record<string, string>>({})
const model = computed(() => models.value.find(item => item.id === modelId.value))
const keys = new Map<string, string>(), sourceJobs = new Map<string, Job>()
let controller = new AbortController(), timer: ReturnType<typeof setTimeout> | undefined
let revision = 0, pollToken: object | null = null, cursor: string | null = null, delay = 2000
let initialized = false, inventoryAt = 0
const terminal = (job: Job) => ['succeeded', 'failed', 'cancelled', 'interrupted'].includes(job.state)
const current = (expected: number, signal: AbortSignal) => !signal.aborted && expected === revision

function error(value: unknown, mutation = false) {
  if (value instanceof DOMException && value.name === 'AbortError') return
  const message = value instanceof ApiClientError ? value.message : mutation ? '操作结果暂时无法确认，请刷新任务或使用同一请求重试。' : '导出状态暂时无法读取，将自动重试。'
  if (mutation) actionWarning.value = message
  else warning.value = message
  if (value instanceof ApiClientError && value.status === 401) emit('error', value)
}
function requestKey(artifactId: string, retryJobId?: string) {
  const identity = retryJobId ? `retry:${retryJobId}` : artifactId
  const storageKey = `edgevision.export.v1:${props.project.id}:${identity}`
  let key = keys.get(identity)
  try {
    if (!key) {
      const saved = sessionStorage.getItem(storageKey)
      if (saved && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(saved)) key = saved
    }
    key ??= crypto.randomUUID()
    sessionStorage.setItem(storageKey, key)
  } catch {
    key ??= crypto.randomUUID()
    storageWarning.value = '浏览器无法保存重试标识。提交结果未确认时，请保留当前页面并使用同一请求重试。'
  }
  keys.set(identity, key)
  return key
}
function invalidate() { revision++; pollToken = null; clearTimeout(timer) }
function resetDetail() { lines.value = []; outputs.value = []; cursor = null; logDone.value = false }
function choose(job: Job) {
  invalidate(); initialized = true; selected.value = job; resetDetail(); void poll()
}
function chooseModel() {
  invalidate(); initialized = true; selected.value = null; resetDetail(); warning.value = ''; actionWarning.value = ''; void poll()
}
async function allArtifacts(projectId: string, signal: AbortSignal) {
  const all: Artifact[] = []
  for (let next = 1; next <= 100; next++) {
    const result = await jobApi.artifacts(projectId, signal, next)
    all.push(...result.items)
    if (all.length >= result.total) return all
    if (!result.items.length) break
  }
  throw new Error('Artifact pagination incomplete')
}
async function poll(forceInventory = false) {
  if (controller.signal.aborted || pollToken) return
  const token = {}; pollToken = token; loading.value = true
  const expected = revision, signal = controller.signal, projectId = props.project.id
  let succeeded = false
  try {
    const result = await jobApi.list(projectId, signal, page.value)
    if (!current(expected, signal)) return
    jobs.value = result.items.filter(item => item.project_id === projectId && item.kind === 'export_onnx')
    total.value = result.total
    if (!initialized && jobs.value[0]) { selected.value = jobs.value[0]; initialized = true; resetDetail() }
    let artifacts: Artifact[] | undefined
    if (forceInventory || !inventoryAt || Date.now() - inventoryAt >= 10000 || selected.value?.state === 'succeeded') {
      artifacts = await allArtifacts(projectId, signal)
      if (!current(expected, signal)) return
      const candidates = artifacts.filter(item => item.project_id === projectId && item.validation_state === 'passed' && ['pt_best', 'pt_last'].includes(item.kind) && item.job_id)
      const eligible: Artifact[] = []
      for (const item of candidates) {
        const id = item.job_id!
        const source = sourceJobs.get(id) ?? await jobApi.detail(id, signal)
        if (!current(expected, signal)) return
        if (source.project_id === projectId && source.kind === 'train' && source.state === 'succeeded') { sourceJobs.set(id, source); eligible.push(item) }
      }
      models.value = eligible; inventoryAt = Date.now()
      if (modelId.value && !eligible.some(item => item.id === modelId.value)) modelId.value = ''
    }
    const id = selected.value?.id
    if (id) {
      const detail = await jobApi.detail(id, signal)
      if (!current(expected, signal)) return
      if (detail.project_id !== projectId || detail.kind !== 'export_onnx') throw new Error('Unexpected export job')
      selected.value = detail
      if (!logDone.value) {
        const logs = await jobApi.logs(id, cursor, signal)
        if (!current(expected, signal)) return
        const last = lines.value.at(-1)?.seq ?? 0
        lines.value = [...lines.value, ...logs.items.filter(line => line.seq > last)].slice(-500)
        cursor = logs.next_cursor; logDone.value = logs.eof
      }
      if (detail.state === 'succeeded') {
        artifacts ??= await allArtifacts(projectId, signal)
        if (!current(expected, signal)) return
        outputs.value = artifacts.filter((item): item is Extract<Artifact, { kind: 'onnx' }> => item.project_id === projectId && item.job_id === id && item.kind === 'onnx' && item.validation_state === 'passed')
      } else outputs.value = []
    }
    warning.value = ''; delay = 2000; succeeded = true
  } catch (value) {
    if (current(expected, signal)) { error(value); delay = Math.min(delay * 2, 15000) }
  } finally {
    if (pollToken === token && current(expected, signal)) {
      pollToken = null; loading.value = false
      timer = setTimeout(() => void poll(), succeeded && selected.value && terminal(selected.value) && !logDone.value ? 100 : delay)
    }
  }
}
function refresh() { invalidate(); void poll(true) }
function changePage(next: number) {
  if (next < 1 || next > Math.max(1, Math.ceil(total.value / 20))) return
  invalidate(); page.value = next; initialized = false; selected.value = null; resetDetail(); void poll()
}
async function submit(replay = false) {
  const artifact = model.value
  if (submitting.value || !artifact || (!replay && acceptedModels.value[artifact.id]) || !props.capability?.available || props.project.archived_at) return
  invalidate(); initialized = true
  const expected = revision, signal = controller.signal, projectId = props.project.id
  const params: ExportOnnxParams = { model_artifact_id: artifact.id, batch: 1, imgsz: 640, precision: 'fp32' }
  const key = requestKey(artifact.id)
  submitting.value = true; actionWarning.value = ''
  try {
    const accepted = await jobApi.exportOnnx(projectId, params, key, signal)
    if (!current(expected, signal)) return
    // Keep this key after acceptance: repeated submission cannot create another job.
    acceptedModels.value = { ...acceptedModels.value, [artifact.id]: accepted.job_id }
    const detail = await jobApi.detail(accepted.job_id, signal)
    if (!current(expected, signal)) return
    if (detail.project_id !== projectId || detail.kind !== 'export_onnx') throw new Error('Unexpected export job')
    page.value = 1; choose(detail)
  } catch (value) { if (current(expected, signal)) error(value, true) }
  finally {
    if (!signal.aborted) submitting.value = false
    if (current(expected, signal)) void poll()
  }
}
function retry() {
  const previous = selected.value
  const id = previous?.export?.source_artifact_id
  if (!previous || !['failed', 'cancelled', 'interrupted'].includes(previous.state) || !id || submitting.value || !models.value.some(item => item.id === id) || !props.capability?.available || props.project.archived_at) return
  modelId.value = id
  // The replacement belongs to this failed job, not to a click. Persisting that
  // identity makes uncertain POSTs and failed detail reads safe across reloads.
  const key = requestKey(id, previous.id)
  if (keys.get(id) !== key) delete acceptedModels.value[id]
  keys.set(id, key)
  try { sessionStorage.setItem(`edgevision.export.v1:${props.project.id}:${id}`, key) }
  catch { storageWarning.value = '浏览器无法保存重试标识。请保留当前页面，避免重复创建任务。' }
  void submit(true)
}
async function cancel() {
  const job = selected.value
  if (!job || cancelling.value || terminal(job) || job.state === 'cancelling') return
  invalidate()
  const expected = revision, signal = controller.signal
  cancelling.value = true; actionWarning.value = ''
  try {
    const result = await jobApi.cancel(job.id, signal)
    if (current(expected, signal) && selected.value?.id === job.id) selected.value = result
  } catch (value) { if (current(expected, signal)) error(value, true) }
  finally {
    if (!signal.aborted) cancelling.value = false
    if (current(expected, signal)) void poll()
  }
}
watch(() => props.project.id, () => {
  controller.abort(); invalidate(); controller = new AbortController()
  models.value = []; modelId.value = ''; jobs.value = []; selected.value = null; resetDetail()
  warning.value = ''; actionWarning.value = ''; storageWarning.value = ''; submitting.value = false; cancelling.value = false; page.value = 1; total.value = 0
  keys.clear(); sourceJobs.clear(); acceptedModels.value = {}; initialized = false; inventoryAt = 0; delay = 2000
  void poll()
}, { immediate: true })
onUnmounted(() => { controller.abort(); invalidate() })
</script>

<template>
  <section class="panel export-panel" aria-label="可信 ONNX 导出">
    <div class="section-title"><h2>ONNX 导出与验证</h2><button :disabled="loading" @click="refresh">刷新导出状态</button></div>
    <p class="note">仅接受本项目成功训练并验证通过的 PT。导出和校验由独立 Worker 执行，不合成百分比或成功结果。</p>
    <p v-if="!capability?.available" class="note">{{ capability?.reason ?? '导出环境尚未验证。' }}</p>
    <p v-if="project.archived_at" class="note">归档项目不能创建导出，历史产物仍可查看。</p>
    <p v-if="warning" class="error" role="alert">{{ warning }}</p>
    <p v-if="actionWarning" class="error" role="alert">{{ actionWarning }}</p>
    <p v-if="storageWarning" class="note" role="status">{{ storageWarning }}</p>
    <form class="grid-form" @submit.prevent="submit()">
      <label>来源模型<select v-model="modelId" required @change="chooseModel"><option value="">选择已验证 PT</option><option v-for="item in models" :key="item.id" :value="item.id">{{ item.kind }} · {{ item.id }} · 训练 {{ item.job_id }}</option></select></label>
      <button class="primary" :disabled="submitting || !model || Boolean(acceptedModels[modelId]) || !capability?.available || Boolean(project.archived_at)">{{ submitting ? '正在提交导出…' : acceptedModels[modelId] ? '已提交导出' : '创建 ONNX 导出任务' }}</button>
    </form>
    <p v-if="!models.length" class="note">暂无符合条件的来源模型。请先完成并验证真实训练。</p>
    <p class="note">固定协议：Linux CPU · YOLO11n · 640×640 · batch 1 · FP32 · opset 18 · 静态输入 · 不含图内 NMS · 不简化。checker、ORT CPU 和三个固定张量的数值比较全部通过后才能下载。</p>
    <dl v-if="model" class="source-identity"><dt>来源产物</dt><dd>{{ model.id }} · {{ model.kind }}</dd><dt>来源训练</dt><dd>{{ model.job_id }}</dd><dt>SHA-256</dt><dd>{{ model.sha256 }}</dd><dt>文件大小</dt><dd>{{ model.size_bytes.toLocaleString() }} bytes</dd></dl>
    <p v-if="acceptedModels[modelId]" class="note">已接收任务 {{ acceptedModels[modelId] }}。可在下方选择任务查看；重复提交沿用同一幂等键。</p>
    <p v-if="!jobs.length" class="note">当前页没有导出任务。任务列表分页包含项目的全部任务类型。</p>
    <div class="actions export-jobs"><button v-for="job in jobs" :key="job.id" :aria-pressed="selected?.id === job.id" @click="choose(job)">{{ job.id }} · {{ job.state }}</button></div>
    <div v-if="total > 20" class="actions"><button :disabled="page <= 1" @click="changePage(page - 1)">上一页导出记录</button><span>第 {{ page }} / {{ Math.ceil(total / 20) }} 页</span><button :disabled="page * 20 >= total" @click="changePage(page + 1)">下一页导出记录</button></div>
    <article v-if="selected" class="export-detail">
      <h3 aria-live="polite">导出任务 · {{ selected.state }}</h3><p class="identity">{{ selected.id }}</p>
      <dl v-if="selected.export" class="source-identity"><dt>冻结来源产物</dt><dd>{{ selected.export.source_artifact_id }}</dd><dt>来源训练</dt><dd>{{ selected.export.source_job_id }}</dd><dt>来源 SHA-256</dt><dd>{{ selected.export.source_sha256 }}</dd></dl>
      <p v-if="selected.error_code" role="status">{{ selected.error_code }}</p>
      <button :disabled="cancelling || terminal(selected) || selected.state === 'cancelling'" @click="cancel">{{ selected.state === 'cancelling' ? '正在停止导出…' : '取消导出' }}</button>
      <button v-if="['failed', 'cancelled', 'interrupted'].includes(selected.state)" :disabled="submitting || !capability?.available || Boolean(project.archived_at) || !models.some(item => item.id === selected?.export?.source_artifact_id)" @click="retry">重新导出（新任务）</button>
      <div class="job-log" role="region" aria-label="导出日志"><p v-if="!lines.length" class="note">暂无日志，未合成进度。</p><ol><li v-for="line in lines" :key="line.seq"><span>{{ line.level }}</span> {{ line.text }}</li></ol><small>{{ logDone ? '已读取最终日志' : '增量读取中' }} · 最多保留最近 500 行</small></div>
      <p v-if="selected.state === 'succeeded' && !outputs.length" class="note">任务已成功，尚未读取到验证通过的 ONNX 产物；不提供未经验证的下载。</p>
      <article v-for="item in outputs" :key="item.id" class="verified-output"><strong>ONNX · passed</strong><p class="identity">SHA-256 {{ item.sha256 }}</p><a :href="`/api/v1/artifacts/${item.id}/download`">下载已验证 ONNX（{{ item.size_bytes.toLocaleString() }} bytes）</a><details><summary>验证与来源追溯</summary><dl class="source-identity"><dt>来源 PT</dt><dd>{{ item.metadata.provenance.parent_artifact_id }}</dd><dt>类别顺序</dt><dd>{{ item.metadata.classes.join('、') }}</dd><dt>实际执行提供方</dt><dd>{{ item.metadata.validation.runtime.provider }}</dd><dt>输入 / 原始输出</dt><dd>{{ item.metadata.validation.input_shape.join(' × ') }} / {{ item.metadata.validation.output_shape.join(' × ') }}</dd><dt>冻结容差</dt><dd>atol {{ item.metadata.validation.atol }} · rtol {{ item.metadata.validation.rtol }}</dd><dt>固定张量验证</dt><dd v-for="sample in item.metadata.validation.samples" :key="sample.name">{{ sample.name }} · 最大绝对误差 {{ sample.max_absolute_error }} · 容差比 {{ sample.max_tolerance_ratio }}</dd><dt>验证记录 SHA-256</dt><dd>{{ item.metadata.validation_sha256 }}</dd><dt>代码 / 环境指纹</dt><dd>{{ item.metadata.provenance.code_version }} / {{ item.metadata.provenance.runtime_binding }}</dd></dl></details></article>
    </article>
    <p class="note">单张图片推理与独立部署包尚不可用。导出校验不代表精度达标或边缘硬件验证。</p>
  </section>
</template>
<style scoped>
.export-panel { min-width: 0; }
.export-panel select { max-width: 100%; min-width: 0; }
.export-panel label { min-width: 0; }
.export-panel .grid-form { grid-template-columns: minmax(0, 1fr) auto; }
@media (max-width: 760px) { .export-panel .grid-form { grid-template-columns: minmax(0, 1fr); } }
.source-identity { display: grid; gap: 8px; }
.source-identity dd { margin: 0; overflow-wrap: anywhere; }
.export-jobs button, .identity, .job-log li { overflow-wrap: anywhere; }
.export-detail, .verified-output { margin-top: 20px; }
</style>
