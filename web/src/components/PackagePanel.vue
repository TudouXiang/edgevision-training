<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { ApiClientError, jobApi } from '../api'
import type { Artifact, Capabilities, PackageParams, Job, JobLog, Project } from '../api'

const props = defineProps<{ userId: string; project: Project; capability?: Capabilities['features'][string] }>()
const emit = defineEmits<{ error: [value: unknown] }>()
const models = ref<Artifact[]>([]), modelId = ref(''), jobs = ref<Job[]>([]), selected = ref<Job | null>(null)
const outputs = ref<Extract<Artifact, { kind: 'deployment_zip' }>[]>([]), lines = ref<JobLog[]>([]), logDone = ref(false)
const warning = ref(''), actionWarning = ref(''), storageWarning = ref(''), loading = ref(false), submitting = ref(false), cancelling = ref(false)
const page = ref(1), total = ref(0), acceptedModels = ref<Record<string, string>>({})
const model = computed(() => models.value.find(item => item.id === modelId.value))
type RequestReceipt = { key: string; sourceJobId?: string; jobId?: string }
const keys = new Map<string, RequestReceipt>(), sourceJobs = new Map<string, Job>()
let controller = new AbortController(), timer: ReturnType<typeof setTimeout> | undefined
let revision = 0, pollToken: object | null = null, cursor: string | null = null, delay = 2000
let initialized = false, inventoryAt = 0
const terminal = (job: Job) => ['succeeded', 'failed', 'cancelled', 'interrupted'].includes(job.state)
const current = (expected: number, signal: AbortSignal) => !signal.aborted && expected === revision

function error(value: unknown, mutation = false) {
  if (value instanceof DOMException && value.name === 'AbortError') return
  const message = value instanceof ApiClientError ? value.message : mutation ? '操作结果暂时无法确认，请刷新任务或使用同一请求重试。' : '打包状态暂时无法读取，将自动重试。'
  if (mutation) actionWarning.value = message
  else warning.value = message
  if (value instanceof ApiClientError && value.status === 401) emit('error', value)
}
function slot(artifactId: string, sourceJobId?: string) {
  return `edgevision.package.v1:${props.userId}:${props.project.id}:${artifactId}${sourceJobId ? `:retry:${sourceJobId}` : ''}`
}
function savedRequest(artifactId: string, sourceJobId?: string): RequestReceipt | undefined {
  const name = slot(artifactId, sourceJobId)
  if (keys.has(name)) return keys.get(name)
  try {
    const raw = sessionStorage.getItem(name)
    if (!raw || raw.length > 2048) return
    const value = JSON.parse(raw)
    if (!value || typeof value !== 'object' || Object.keys(value).some(key => !['key', 'sourceJobId', 'jobId'].includes(key))) return
    if (typeof value.key !== 'string' || !/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(value.key)) return
    if (['sourceJobId', 'jobId'].some(key => value[key] !== undefined && (typeof value[key] !== 'string' || !value[key] || value[key].length > 128))) return
    if (sourceJobId && value.sourceJobId !== sourceJobId) return
    keys.set(name, value); return value
  } catch { storageWarning.value = '浏览器无法恢复重试标识。请保留当前页面并确认已有任务。' }
}
function saveRequest(artifactId: string, value: RequestReceipt) {
  const names = [slot(artifactId), ...(value.sourceJobId ? [slot(artifactId, value.sourceJobId)] : [])]
  for (const name of names) {
    keys.set(name, value)
    try { sessionStorage.setItem(name, JSON.stringify(value)) }
    catch { storageWarning.value = '浏览器无法保存重试标识。提交结果未确认时，请保留当前页面并使用同一请求重试。' }
  }
}
function requestReceipt(artifactId: string, sourceJobId?: string) {
  const receipt = savedRequest(artifactId, sourceJobId) ?? { key: crypto.randomUUID(), ...(sourceJobId ? { sourceJobId } : {}) }
  saveRequest(artifactId, receipt)
  return receipt
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
    jobs.value = result.items.filter(item => item.project_id === projectId && item.kind === 'package')
    total.value = result.total
    if (!initialized && jobs.value[0]) { selected.value = jobs.value[0]; initialized = true; resetDetail() }
    let artifacts: Artifact[] | undefined
    if (forceInventory || !inventoryAt || Date.now() - inventoryAt >= 10000 || selected.value?.state === 'succeeded') {
      artifacts = await allArtifacts(projectId, signal)
      if (!current(expected, signal)) return
      const candidates = artifacts.filter(item => item.project_id === projectId && item.validation_state === 'passed' && item.kind === 'onnx' && item.format === 'onnx' && item.job_id)
      const eligible: Artifact[] = []
      for (const item of candidates) {
        const id = item.job_id!
        const source = sourceJobs.get(id) ?? await jobApi.detail(id, signal)
        if (!current(expected, signal)) return
        if (source.project_id === projectId && source.id === id && source.kind === 'export_onnx' && source.state === 'succeeded') { sourceJobs.set(id, source); eligible.push(item) }
      }
      models.value = eligible; inventoryAt = Date.now()
      for (const item of eligible) { const saved = savedRequest(item.id); if (saved?.jobId) acceptedModels.value[item.id] = saved.jobId }
      if (modelId.value && !eligible.some(item => item.id === modelId.value)) modelId.value = ''
    }
    const id = selected.value?.id
    if (id) {
      const detail = await jobApi.detail(id, signal)
      if (!current(expected, signal)) return
      if (detail.id !== id || detail.project_id !== projectId || detail.kind !== 'package') throw new Error('Unexpected package job')
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
        outputs.value = artifacts.filter((item): item is Extract<Artifact, { kind: 'deployment_zip' }> => item.project_id === projectId && item.job_id === id && item.kind === 'deployment_zip' && item.validation_state === 'passed')
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
async function submit(sourceJobId?: string) {
  const artifact = model.value
  if (submitting.value || !artifact || (!sourceJobId && acceptedModels.value[artifact.id]) || !props.capability?.available || props.project.archived_at) return
  invalidate(); initialized = true
  const expected = revision, signal = controller.signal, projectId = props.project.id
  const params: PackageParams = { onnx_artifact_id: artifact.id }
  const receipt = requestReceipt(artifact.id, sourceJobId)
  submitting.value = true; actionWarning.value = ''
  try {
    const accepted = receipt.jobId ? { job_id: receipt.jobId } : await jobApi.package(projectId, params, receipt.key, signal, receipt.sourceJobId)
    if (!current(expected, signal)) return
    // Persist acceptance before reading details; a failed read must not create another job.
    saveRequest(artifact.id, { ...receipt, jobId: accepted.job_id })
    acceptedModels.value = { ...acceptedModels.value, [artifact.id]: accepted.job_id }
    const detail = await jobApi.detail(accepted.job_id, signal)
    if (!current(expected, signal)) return
    if (detail.id !== accepted.job_id || detail.project_id !== projectId || detail.kind !== 'package' || detail.package?.onnx_artifact_id !== artifact.id || (detail.source_job_id ?? undefined) !== receipt.sourceJobId) throw new Error('Unexpected package job')
    page.value = 1; choose(detail)
  } catch (value) { if (current(expected, signal)) error(value, true) }
  finally {
    if (!signal.aborted) submitting.value = false
    if (current(expected, signal)) void poll()
  }
}
function retry() {
  const previous = selected.value, id = previous?.package?.onnx_artifact_id
  if (!previous || !['failed', 'cancelled', 'interrupted'].includes(previous.state) || !id || submitting.value || !models.value.some(item => item.id === id) || !props.capability?.available || props.project.archived_at) return
  modelId.value = id
  void submit(previous.id)
}
async function showAccepted() {
  const id = acceptedModels.value[modelId.value]
  if (!id) return
  invalidate()
  const expected = revision, signal = controller.signal, projectId = props.project.id
  try {
    const detail = await jobApi.detail(id, signal)
    if (!current(expected, signal)) return
    if (detail.id !== id || detail.project_id !== projectId || detail.kind !== 'package') throw new Error('Unexpected package job')
    choose(detail)
  } catch (value) { if (current(expected, signal)) { error(value, true); void poll() } }
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
watch(() => [props.userId, props.project.id], () => {
  controller.abort(); invalidate(); controller = new AbortController()
  models.value = []; modelId.value = ''; jobs.value = []; selected.value = null; resetDetail()
  warning.value = ''; actionWarning.value = ''; storageWarning.value = ''; submitting.value = false; cancelling.value = false; page.value = 1; total.value = 0
  keys.clear(); sourceJobs.clear(); acceptedModels.value = {}; initialized = false; inventoryAt = 0; delay = 2000
  void poll()
}, { immediate: true })
onUnmounted(() => { controller.abort(); invalidate() })
</script>

<template>
  <section class="panel package-panel" aria-label="独立部署包">
    <div class="section-title"><h2>独立部署包</h2><button :disabled="loading" @click="refresh">刷新打包状态</button></div>
    <p class="note">将已验证 ONNX、固定推理脚本、依赖锁和来源说明打包，供独立 Linux CPU 环境准备部署。</p>
    <p class="note">ZIP 不包含 Python 解释器或 wheels。首次准备依赖需要联网，或另备匹配平台与架构的 wheelhouse；不是开箱即用的离线包。</p>
    <p v-if="!capability?.available" class="note">{{ capability?.reason ?? '独立部署环境尚未验证。' }}</p>
    <p v-if="project.archived_at" class="note">归档项目不能创建打包任务，历史产物仍可查看。</p>
    <p v-if="warning" class="error" role="alert">{{ warning }}</p><p v-if="actionWarning" class="error" role="alert">{{ actionWarning }}</p>
    <p v-if="storageWarning" class="note" role="status">{{ storageWarning }}</p>
    <form class="grid-form" @submit.prevent="submit()">
      <label>来源 ONNX<select v-model="modelId" required @change="chooseModel"><option value="">选择已验证 ONNX</option><option v-for="item in models" :key="item.id" :value="item.id">{{ item.id }} · 导出 {{ item.job_id }}</option></select></label>
      <button class="primary" :disabled="submitting || !model || Boolean(acceptedModels[modelId]) || !capability?.available || Boolean(project.archived_at)">{{ submitting ? '正在提交打包…' : acceptedModels[modelId] ? '已提交打包' : '创建独立部署包' }}</button>
    </form>
    <p v-if="!models.length" class="note">暂无符合条件的 ONNX。请先完成训练和可信 ONNX 导出。</p>
    <dl v-if="model" class="source-identity"><dt>来源产物</dt><dd>{{ model.id }}</dd><dt>来源导出</dt><dd>{{ model.job_id }}</dd><dt>SHA-256</dt><dd>{{ model.sha256 }}</dd></dl>
    <p v-if="acceptedModels[modelId]" class="note">已接收任务 {{ acceptedModels[modelId] }}。<button @click="showAccepted">查看已接收任务</button></p>
    <p v-if="!jobs.length" class="note">当前页没有打包任务。分页包含项目的全部任务类型。</p>
    <div class="actions package-jobs"><button v-for="job in jobs" :key="job.id" :aria-pressed="selected?.id === job.id" @click="choose(job)">{{ job.id }} · {{ job.state }}</button></div>
    <div v-if="total > 20" class="actions"><button :disabled="page <= 1" @click="changePage(page - 1)">上一页打包记录</button><span>第 {{ page }} / {{ Math.ceil(total / 20) }} 页</span><button :disabled="page * 20 >= total" @click="changePage(page + 1)">下一页打包记录</button></div>
    <article v-if="selected" class="package-detail">
      <h3 aria-live="polite">打包任务 · {{ selected.state }}</h3><p class="identity">{{ selected.id }}</p>
      <dl v-if="selected.package" class="source-identity"><dt>冻结 ONNX</dt><dd>{{ selected.package.onnx_artifact_id }}</dd><dt>来源导出</dt><dd>{{ selected.package.export_job_id }}</dd><dt>来源 SHA-256</dt><dd>{{ selected.package.source_sha256 }}</dd></dl>
      <p v-if="selected.error_code" role="status">{{ selected.error_code }}</p>
      <button :disabled="cancelling || terminal(selected) || selected.state === 'cancelling'" @click="cancel">{{ selected.state === 'cancelling' ? '正在停止打包…' : '取消打包' }}</button>
      <button v-if="['failed', 'cancelled', 'interrupted'].includes(selected.state)" :disabled="submitting || !capability?.available || Boolean(project.archived_at) || !models.some(item => item.id === selected?.package?.onnx_artifact_id)" @click="retry">重新打包（新任务）</button>
      <div class="job-log" role="region" aria-label="打包日志"><p v-if="!lines.length" class="note">暂无日志，未合成进度。</p><ol><li v-for="line in lines" :key="line.seq"><span>{{ line.level }}</span> {{ line.text }}</li></ol><small>{{ logDone ? '已读取最终日志' : '增量读取中' }} · 最多保留最近 500 行</small></div>
      <p v-if="selected.state === 'succeeded' && !outputs.length" class="note">尚未读取到完整性验证通过的部署包，不提供未经验证的下载。</p>
      <article v-for="item in outputs" :key="item.id" class="verified-output">
        <strong>部署 ZIP · 完整性验证通过</strong><p class="identity">SHA-256 {{ item.sha256 }}</p>
        <a :href="`/api/v1/artifacts/${encodeURIComponent(item.id)}/download`">下载独立部署包（{{ item.size_bytes.toLocaleString() }} bytes）</a>
        <details><summary>来源与验证范围</summary><dl class="source-identity"><dt>来源 ONNX</dt><dd>{{ item.metadata.provenance.onnx_artifact_id }}</dd><dt>目标环境</dt><dd>{{ item.metadata.template.target }}</dd><dt>模板证明 SHA-256</dt><dd>{{ item.metadata.template_validation_sha256 }}</dd><dt>清单 SHA-256</dt><dd>{{ item.metadata.manifest_sha256 }}</dd></dl></details>
      </article>
    </article>
    <p class="note">每个任务仅验证来源、文件完整性和固定包结构，不会逐包执行模型。模板独立运行验证不代表模型精度、GPU/NPU 或目标硬件已验收。</p>
  </section>
</template>
<style scoped>
.package-panel, .package-panel label { min-width: 0; }
.package-panel select { max-width: 100%; min-width: 0; }
.package-panel .grid-form { grid-template-columns: minmax(0, 1fr) auto; }
@media (max-width: 760px) { .package-panel .grid-form { grid-template-columns: minmax(0, 1fr); } }
.source-identity { display: grid; gap: 8px; }
.source-identity dd { margin: 0; overflow-wrap: anywhere; }
.package-jobs button, .identity, .job-log li { overflow-wrap: anywhere; }
.package-detail, .verified-output { margin-top: 20px; }
</style>
