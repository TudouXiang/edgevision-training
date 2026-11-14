<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { ApiClientError, inferenceApi, jobApi } from '../api'
import type { Artifact, Capabilities, InferenceInput, InferenceParams, InferenceResult, Job, JobLog, Project } from '../api'
import { inferenceRequests, sameInferenceParams, validThreshold } from './inferenceRequests'
import type { InferenceRequest } from './inferenceRequests'
const props = defineProps<{ userId: string; project: Project; ptCapability?: Capabilities['features'][string]; onnxCapability?: Capabilities['features'][string] }>()
const emit = defineEmits<{ error: [value: unknown] }>()
const models = ref<Artifact[]>([]), inputs = ref<InferenceInput[]>([]), jobs = ref<Job[]>([])
const backend = ref<InferenceParams['backend']>('onnx'), modelId = ref(''), inputId = ref(''), confidence = ref<number | string>(.25), iou = ref<number | string>(.45)
const file = ref<File | null>(null), fileInput = ref<HTMLInputElement | null>(null)
const selectedId = ref(''), selected = ref<Job | null>(null), result = ref<InferenceResult | null>(null), previewUrl = ref('')
const lines = ref<JobLog[]>([]), logDone = ref(false), warning = ref(''), actionWarning = ref(''), storageWarning = ref('')
const uploading = ref(false), submitting = ref(false), cancelling = ref(false), loading = ref(false), page = ref(1), total = ref(0)
const activeRequest = ref<InferenceRequest | null>(null), pendingRequest = ref<InferenceRequest | null>(null)
const capability = computed(() => backend.value === 'pt' ? props.ptCapability : props.onnxCapability)
const modelBackend = (item: Artifact): InferenceParams['backend'] => item.kind === 'onnx' ? 'onnx' : 'pt'
const matchingModels = computed(() => models.value.filter(item => modelBackend(item) === backend.value))
const model = computed(() => matchingModels.value.find(item => item.id === modelId.value)), input = computed(() => inputs.value.find(item => item.id === inputId.value))
const params = computed<InferenceParams | null>(() => model.value && input.value && validThreshold(confidence.value) && validThreshold(iou.value)
  ? { model_artifact_id: model.value.id, image_artifact_id: input.value.id, backend: backend.value, confidence: confidence.value, iou: iou.value } : null)
const draftParams = computed<InferenceParams | null>(() => modelId.value && inputId.value && validThreshold(confidence.value) && validThreshold(iou.value)
  ? { model_artifact_id: modelId.value, image_artifact_id: inputId.value, backend: backend.value, confidence: confidence.value, iou: iou.value } : null)
const matchesDraft = (record: InferenceRequest) => Boolean(draftParams.value && sameInferenceParams(record.params, draftParams.value))
const terminal = (job: Job) => ['succeeded', 'failed', 'cancelled', 'interrupted'].includes(job.state)
const canRetry = computed(() => { const p = selected.value?.inference?.params; return p && models.value.some(item => item.id === p.model_artifact_id && modelBackend(item) === p.backend) && inputs.value.some(item => item.id === p.image_artifact_id) && (p.backend === 'pt' ? props.ptCapability : props.onnxCapability)?.available && !props.project.archived_at })
let scope = new AbortController(), readController = new AbortController(), actionController = new AbortController()
let revision = 0, pollToken: object | null = null, timer: ReturnType<typeof setTimeout> | undefined
let cursor: string | null = null, delay = 2000, inventoryAt = 0, initialized = false
const sources = new Map<string, Job>()
function storageProblem() { storageWarning.value = '浏览器无法可靠保存恢复标识。提交结果未确认时，请保留当前页面并使用同一请求重试，避免重复创建任务。' }
let requests = inferenceRequests(props.userId, props.project.id, storageProblem)
const current = (expected: number, signal: AbortSignal) => !scope.signal.aborted && !signal.aborted && expected === revision
function error(value: unknown, mutation = false) {
  if (value instanceof DOMException && value.name === 'AbortError') return
  const message = value instanceof ApiClientError ? value.message : mutation ? '操作结果暂时无法确认。推理提交可使用同一请求重试；上传不保证幂等，请先刷新输入列表。' : '推理状态暂时无法读取，将自动重试。'
  if (mutation) actionWarning.value = message; else warning.value = message
  if (value instanceof ApiClientError && value.status === 401) emit('error', value)
}
function clearResult() { result.value = null; if (previewUrl.value) URL.revokeObjectURL(previewUrl.value); previewUrl.value = '' }
function clearDetail() { selected.value = null; lines.value = []; cursor = null; logDone.value = false; clearResult() }
function invalidate() {
  revision++; clearTimeout(timer); pollToken = null
  readController.abort(); actionController.abort(); readController = new AbortController(); actionController = new AbortController()
  loading.value = false; uploading.value = false; submitting.value = false; cancelling.value = false
}
function editForm() {
  const wasUploading = uploading.value
  invalidate(); initialized = true; selectedId.value = ''; clearDetail(); warning.value = ''
  activeRequest.value = draftParams.value ? requests.forParams(draftParams.value) : null
  if (activeRequest.value && !activeRequest.value.job_id) pendingRequest.value = activeRequest.value
  actionWarning.value = wasUploading ? '上传请求已停止等待，服务器可能已保存输入。请刷新输入列表；再次上传可能创建不同输入。' : ''
  void poll()
}
function changeBackend() { modelId.value = ''; editForm() }
function choose(job: Job) { invalidate(); initialized = true; selectedId.value = job.id; clearDetail(); selected.value = job; actionWarning.value = ''; void poll() }
function chooseFile(event: Event) { editForm(); file.value = (event.target as HTMLInputElement).files?.[0] ?? null }
async function allArtifacts(projectId: string, signal: AbortSignal) {
  const all: Artifact[] = []
  for (let next = 1; next <= 100; next++) { const response = await jobApi.artifacts(projectId, signal, next); all.push(...response.items); if (all.length >= response.total) return all; if (!response.items.length) break }
  throw new Error('Incomplete artifact pagination')
}
function validJob(job: Job, id: string, projectId: string) { if (job.id !== id || job.project_id !== projectId || job.kind !== 'infer') throw new Error('Unexpected inference job'); return job }
async function poll(forceInventory = false) {
  if (scope.signal.aborted || pollToken) return
  const token = {}; pollToken = token; loading.value = true
  const expected = revision, signal = readController.signal, projectId = props.project.id
  let success = false
  try {
    const response = await jobApi.list(projectId, signal, page.value)
    if (!current(expected, signal)) return
    jobs.value = response.items.filter(item => item.project_id === projectId && item.kind === 'infer'); total.value = response.total
    if (!initialized) { selectedId.value ||= jobs.value[0]?.id ?? ''; initialized = true }
    let artifacts: Artifact[] | undefined
    if (forceInventory || !inventoryAt || Date.now() - inventoryAt >= 10000) {
      artifacts = await allArtifacts(projectId, signal); if (!current(expected, signal)) return
      const candidates = artifacts.filter(item => item.project_id === projectId && item.validation_state === 'passed' && ((['pt_best', 'pt_last'].includes(item.kind) && item.format === 'pt') || (item.kind === 'onnx' && item.format === 'onnx')) && item.job_id)
      const eligible: Artifact[] = []
      for (const item of candidates) {
        const id = item.job_id!, source = sources.get(id) ?? await jobApi.detail(id, signal)
        if (!current(expected, signal)) return
        if (source.id === id && source.project_id === projectId && source.state === 'succeeded' && source.kind === (item.kind === 'onnx' ? 'export_onnx' : 'train')) { sources.set(id, source); eligible.push(item) }
      }
      models.value = eligible
      inputs.value = artifacts.filter((item): item is InferenceInput => item.project_id === projectId && item.kind === 'inference_input' && item.validation_state === 'unverified' && item.job_id === null)
      inventoryAt = Date.now()
    }
    const id = selectedId.value
    if (id) {
      const detail = validJob(await jobApi.detail(id, signal), id, projectId); if (!current(expected, signal)) return
      selected.value = detail
      if (!logDone.value) {
        const logs = await jobApi.logs(id, cursor, signal); if (!current(expected, signal)) return
        const last = lines.value.at(-1)?.seq ?? 0
        lines.value = [...lines.value, ...logs.items.filter(line => line.seq > last)].slice(-500); cursor = logs.next_cursor; logDone.value = logs.eof
      }
      if (detail.state === 'succeeded' && !result.value) {
        artifacts ??= await allArtifacts(projectId, signal); if (!current(expected, signal)) return
        const output = artifacts.find(item => item.project_id === projectId && item.job_id === id && item.kind === 'inference_result' && item.validation_state === 'passed')
        if (output) {
          const value = await inferenceApi.result(output.id, signal); if (!current(expected, signal)) return
          if (!detail.inference || value.artifact_id !== output.id || value.provenance.job_id !== id || value.provenance.project_id !== projectId
            || value.params.model_artifact_id !== detail.inference.model_artifact_id || value.params.image_artifact_id !== detail.inference.image_artifact_id
            || (['backend', 'confidence', 'iou'] as const).some(key => value.params[key] !== detail.inference!.params[key])
            || value.backend !== detail.inference.params.backend || value.provider !== (value.backend === 'pt' ? 'pytorch_cpu' : 'CPUExecutionProvider')
            || value.image_url !== `/api/v1/inferences/${encodeURIComponent(output.id)}/image`) throw new Error('Unexpected inference result')
          result.value = value
        }
      } else if (detail.state !== 'succeeded') clearResult()
      if (result.value && !previewUrl.value) { const blob = await inferenceApi.preview(result.value.artifact_id, signal); if (!current(expected, signal)) return; previewUrl.value = URL.createObjectURL(blob) }
    }
    warning.value = ''; delay = 2000; success = true
  } catch (value) { if (current(expected, signal)) { error(value); delay = Math.min(delay * 2, 15000) } }
  finally {
    if (pollToken === token && current(expected, signal)) { pollToken = null; loading.value = false; timer = setTimeout(() => void poll(), success && selected.value && terminal(selected.value) && !logDone.value ? 100 : delay) }
  }
}
function refresh() { invalidate(); void poll(true) }
function changePage(next: number) { if (next < 1 || next > Math.max(1, Math.ceil(total.value / 20))) return; invalidate(); page.value = next; initialized = false; selectedId.value = ''; clearDetail(); void poll() }
async function upload() {
  const chosen = file.value
  if (!chosen || uploading.value || submitting.value || props.project.archived_at) return
  if (!/\.(jpe?g|png)$/i.test(chosen.name) || !['image/jpeg', 'image/png', 'application/octet-stream', ''].includes(chosen.type) || chosen.size <= 0 || chosen.size > 50 * 1024 * 1024) { actionWarning.value = '请选择非空 JPEG/PNG，文件不能超过 50 MiB；实际格式与安全解码由 Worker 校验。'; return }
  invalidate(); initialized = true; selectedId.value = ''; clearDetail(); activeRequest.value = null
  const expected = revision, signal = actionController.signal, projectId = props.project.id
  uploading.value = true; actionWarning.value = ''
  try {
    const uploaded = await inferenceApi.upload(projectId, chosen, signal); if (!current(expected, signal)) return
    if (uploaded.project_id !== projectId || uploaded.kind !== 'inference_input' || uploaded.validation_state !== 'unverified' || uploaded.job_id !== null) throw new Error('Unexpected uploaded input')
    inputs.value = [...inputs.value.filter(item => item.id !== uploaded.id), uploaded]; inputId.value = uploaded.id
    file.value = null; if (fileInput.value) fileInput.value.value = ''; inventoryAt = 0
  } catch (value) { if (current(expected, signal)) error(value, true) }
  finally { if (current(expected, signal)) { uploading.value = false; void poll() } }
}
async function submit(source?: string, previous?: InferenceParams) {
  const p = previous ?? params.value, feature = p?.backend === 'pt' ? props.ptCapability : props.onnxCapability
  if (!p || submitting.value || uploading.value || cancelling.value || props.project.archived_at || !feature?.available) return
  if (!models.value.some(item => item.id === p.model_artifact_id && modelBackend(item) === p.backend) || !inputs.value.some(item => item.id === p.image_artifact_id) || !validThreshold(p.confidence) || !validThreshold(p.iou)) return
  // Edits never erase the last operation for these exact parameters, including
  // its retry origin. Only an explicit retry of another terminal job rotates it.
  const existing = source === undefined ? requests.forParams(p) : null
  await sendRequest(existing ?? requests.get(p, source))
}
function recoverPending() {
  const record = pendingRequest.value
  // Recovery replays only the persisted request. It never allocates a new key,
  // substitutes form fields, or bypasses the server's current authorization.
  if (record && !record.job_id) void sendRequest(record)
}
async function sendRequest(record: InferenceRequest) {
  if (submitting.value || uploading.value || cancelling.value) return
  const receiptStore = requests
  receiptStore.save(record, true)
  invalidate(); initialized = true; clearDetail(); activeRequest.value = matchesDraft(record) ? record : null; selectedId.value = record.job_id ?? ''
  if (!record.job_id) pendingRequest.value = record
  const expected = revision, signal = actionController.signal, projectId = props.project.id
  submitting.value = true; actionWarning.value = ''
  try {
    if (!record.job_id) {
      const accepted = await jobApi.infer(projectId, record.params, record.key, signal, record.source_job_id); if (!current(expected, signal)) return
      record.job_id = accepted.job_id; receiptStore.save(record, true) // Save acceptance before detail reads.
      activeRequest.value = matchesDraft(record) ? { ...record } : null; selectedId.value = accepted.job_id
      if (pendingRequest.value?.key === record.key) pendingRequest.value = null
    }
    page.value = 1
  } catch (value) { if (current(expected, signal)) error(value, true) }
  finally { if (current(expected, signal)) { submitting.value = false; void poll() } }
}
function retry() {
  const job = selected.value
  if (!job?.inference || !['failed', 'cancelled', 'interrupted'].includes(job.state) || !canRetry.value) return
  const p = job.inference.params
  backend.value = p.backend; modelId.value = p.model_artifact_id; inputId.value = p.image_artifact_id; confidence.value = p.confidence; iou.value = p.iou
  void submit(job.id, p)
}
async function cancel() {
  const job = selected.value
  if (!job || cancelling.value || terminal(job) || job.state === 'cancelling') return
  invalidate(); const expected = revision, signal = actionController.signal, projectId = props.project.id
  cancelling.value = true; actionWarning.value = ''
  try { const value = validJob(await jobApi.cancel(job.id, signal), job.id, projectId); if (current(expected, signal)) selected.value = value }
  catch (value) { if (current(expected, signal)) error(value, true) }
  finally { if (current(expected, signal)) { cancelling.value = false; void poll() } }
}
watch(() => [props.userId, props.project.id], () => {
  scope.abort(); invalidate(); scope = new AbortController()
  models.value = []; inputs.value = []; jobs.value = []; modelId.value = ''; inputId.value = ''; backend.value = 'onnx'; confidence.value = .25; iou.value = .45
  selectedId.value = ''; clearDetail(); file.value = null; if (fileInput.value) fileInput.value.value = ''
  warning.value = ''; actionWarning.value = ''; storageWarning.value = ''; page.value = 1; total.value = 0; activeRequest.value = null; pendingRequest.value = null
  sources.clear(); inventoryAt = 0; initialized = false; delay = 2000; requests = inferenceRequests(props.userId, props.project.id, storageProblem)
  const saved = requests.last()
  if (saved) { activeRequest.value = saved; pendingRequest.value = saved.job_id ? null : saved; backend.value = saved.params.backend; modelId.value = saved.params.model_artifact_id; inputId.value = saved.params.image_artifact_id; confidence.value = saved.params.confidence; iou.value = saved.params.iou; selectedId.value = saved.job_id ?? ''; initialized = true }
  void poll()
}, { immediate: true })
onUnmounted(() => { scope.abort(); invalidate(); clearResult() })
</script>

<template>
  <section class="panel inference-panel" aria-label="真实单图推理">
    <div class="section-title"><h2>单张图片推理</h2><button :disabled="uploading || submitting || cancelling" :aria-busy="loading" @click="refresh">刷新推理状态</button></div>
    <p class="note">JPEG / PNG · 可信 PT 或 ONNX · CPU · Worker 单重任务队列。上传只保存未验证原字节，202 仅表示任务已接收；不生成模拟检测或进度。</p>
    <p v-if="!capability?.available" class="note">{{ backend.toUpperCase() }}：{{ capability?.reason ?? '当前推理环境尚未验证。' }}</p>
    <p v-if="project.archived_at" class="note">归档项目仅可读取历史和取消已有任务，不能上传或创建新推理。</p>
    <p v-if="warning" role="alert" class="error">{{ warning }}</p><p v-if="actionWarning" role="alert" class="error">{{ actionWarning }}</p><p v-if="storageWarning" role="status" class="note">{{ storageWarning }}</p>
    <form class="inference-upload" @submit.prevent="upload"><label>上传单张图片<input ref="fileInput" type="file" accept=".jpg,.jpeg,.png,image/jpeg,image/png" :disabled="Boolean(project.archived_at)" @change="chooseFile" /></label><button type="submit" :disabled="!file || uploading || submitting || Boolean(project.archived_at)">{{ uploading ? '正在上传原字节…' : '上传未验证输入' }}</button></form>
    <p class="note">最大 50 MiB。上传没有幂等保证，同一图片再次上传可能产生不同的不可变输入。原输入不提供预览或下载。</p>
    <form class="grid-form inference-form" @submit.prevent="submit()">
      <label>执行后端<select v-model="backend" @change="changeBackend"><option value="onnx">ONNX</option><option value="pt">PT</option></select></label>
      <label>来源模型<select v-model="modelId" required @change="editForm"><option value="">选择本项目 passed 模型</option><option v-for="item in matchingModels" :key="item.id" :value="item.id">{{ item.kind }} · {{ item.id }}</option></select></label>
      <label>不可变图片输入<select v-model="inputId" required @change="editForm"><option value="">选择已上传的 unverified 输入</option><option v-for="item in inputs" :key="item.id" :value="item.id">{{ item.format }} · {{ item.id }} · unverified</option></select></label>
      <label>置信度阈值<input v-model.number="confidence" type="number" min="0" max="1" step="any" required @input="editForm" /></label><label>IoU 阈值<input v-model.number="iou" type="number" min="0" max="1" step="any" required @input="editForm" /></label>
      <button class="primary" :disabled="!params || uploading || submitting || !capability?.available || Boolean(project.archived_at) || Boolean(activeRequest?.job_id)">{{ submitting ? '正在提交推理…' : activeRequest?.job_id ? '已接收推理任务' : activeRequest ? '使用同一请求重试提交' : '创建推理任务' }}</button>
    </form>
    <p v-if="!matchingModels.length" class="note">当前后端没有可用模型。仅列出本项目已成功训练的 passed PT，或已成功导出的 passed ONNX；不会自动换后端。</p>
    <p v-if="!validThreshold(confidence) || !validThreshold(iou)" class="error">阈值必须是 0 到 1 的有限数字。</p>
    <dl v-if="model || input" class="source-identity"><template v-if="model"><dt>所选模型 / 来源任务</dt><dd>{{ model.id }} / {{ model.job_id }}</dd><dt>模型 SHA-256</dt><dd>{{ model.sha256 }}</dd></template><template v-if="input"><dt>原输入状态</dt><dd>{{ input.id }} · unverified · {{ input.size_bytes.toLocaleString() }} bytes</dd><dt>原字节 SHA-256</dt><dd>{{ input.sha256 }}</dd></template></dl>
    <p v-if="activeRequest?.job_id" class="note">已接收任务 {{ activeRequest.job_id }}。刷新或重新进入页面会恢复该任务；详情暂时不可读也不会再次创建。</p><div v-if="pendingRequest" class="pending-recovery"><p class="note">已保留提交参数和幂等标识。响应丢失不代表任务未创建。此入口只重放原请求，不更换参数或标识；若原任务未被接收且当前条件不允许创建，服务器会明确拒绝。</p><p class="identity">原请求：{{ pendingRequest.params.backend }} · 模型 {{ pendingRequest.params.model_artifact_id }} · 输入 {{ pendingRequest.params.image_artifact_id }} · confidence {{ pendingRequest.params.confidence }} · IoU {{ pendingRequest.params.iou }} · 重试来源 {{ pendingRequest.source_job_id ?? '无' }}</p><button :disabled="submitting || uploading || cancelling" @click="recoverPending">恢复未确认提交（同一请求）</button></div>
    <p v-if="!jobs.length" class="note">当前页没有推理任务。分页总数包含项目的所有任务类型。</p>
    <div class="actions inference-jobs"><button v-for="job in jobs" :key="job.id" :aria-pressed="selectedId === job.id" @click="choose(job)">{{ job.id }} · {{ job.state }}</button></div>
    <div v-if="total > 20" class="actions"><button :disabled="page <= 1" @click="changePage(page - 1)">上一页推理记录</button><span>第 {{ page }} / {{ Math.ceil(total / 20) }} 页</span><button :disabled="page * 20 >= total" @click="changePage(page + 1)">下一页推理记录</button></div>
    <p v-if="selectedId && !selected" class="note">正在读取任务 {{ selectedId }}，尚未取得状态。</p>
    <article v-if="selected" class="inference-detail">
      <h3 aria-live="polite">推理任务 · {{ selected.state }}</h3><p class="identity">{{ selected.id }}</p>
      <dl v-if="selected.inference" class="source-identity"><dt>冻结模型 / 原输入</dt><dd>{{ selected.inference.model_artifact_id }} / {{ selected.inference.image_artifact_id }}</dd><dt>请求后端 / 阈值</dt><dd>{{ selected.inference.params.backend }} · confidence {{ selected.inference.params.confidence }} · IoU {{ selected.inference.params.iou }}</dd><dt>原字节 SHA-256</dt><dd>{{ selected.inference.image_sha256 }}</dd><dt>来源任务（显式重试）</dt><dd>{{ selected.source_job_id ?? '无' }}</dd></dl>
      <p v-if="selected.error_code" role="status">{{ selected.error_code }}</p><div class="actions"><button :disabled="cancelling || terminal(selected) || selected.state === 'cancelling'" @click="cancel">{{ selected.state === 'cancelling' ? '正在停止推理…' : '取消推理' }}</button><button v-if="['failed', 'cancelled', 'interrupted'].includes(selected.state)" :disabled="submitting || uploading || !canRetry" @click="retry">重新推理（新任务）</button></div>
      <div class="job-log" role="region" aria-label="推理日志"><p v-if="!lines.length" class="note">暂无日志，未合成进度。</p><ol><li v-for="line in lines" :key="line.seq"><span>{{ line.level }}</span> {{ line.text }}</li></ol><small>{{ logDone ? '已读取最终日志' : '增量读取中' }} · 最多保留最近 500 行</small></div>
      <p v-if="selected.state === 'succeeded' && !result" class="note">任务已成功，尚未读取到该任务的验证结果，不显示猜测结果。</p>
      <article v-if="result" class="verified-inference"><h4>真实结果 · {{ result.detections.length }} 个检测框</h4>
        <dl class="source-identity"><dt>实际后端 / provider</dt><dd>{{ result.backend }} / {{ result.provider }}</dd><dt>EXIF 校正后原图尺寸</dt><dd>{{ result.image_width }} × {{ result.image_height }} px</dd><dt>净化预览尺寸</dt><dd>{{ result.preview.width }} × {{ result.preview.height }} px</dd><dt>类别顺序</dt><dd>{{ result.classes.join('、') }}</dd><dt>实际阈值 / 协议</dt><dd>confidence {{ result.params.confidence }} · IoU {{ result.params.iou }} · {{ result.protocol }}</dd><dt>单图耗时（非性能基准）</dt><dd>{{ result.timings.total }} ms · 模型执行 {{ result.timings.infer }} ms</dd></dl>
        <p class="note">检测坐标属于 EXIF 校正后的原图，预览仅用于等比例显示；不使用编码前尺寸定位框。</p>
        <svg v-if="previewUrl" class="inference-preview" :viewBox="`0 0 ${result.image_width} ${result.image_height}`" role="img" aria-label="净化图片与真实检测框"><image :href="previewUrl" x="0" y="0" :width="result.image_width" :height="result.image_height" preserveAspectRatio="none" /><rect v-for="(detection, index) in result.detections" :key="index" :x="detection.xyxy[0]" :y="detection.xyxy[1]" :width="detection.xyxy[2] - detection.xyxy[0]" :height="detection.xyxy[3] - detection.xyxy[1]"><title>{{ result.classes[detection.class_id] }} · {{ detection.score }}</title></rect></svg>
        <p v-else class="note">净化预览尚未读取，正在重试。</p><p v-if="!result.detections.length" class="note">本次结果没有检测框。这是合法的空检测成功结果。</p><ol v-else class="detections"><li v-for="(detection, index) in result.detections" :key="index">{{ result.classes[detection.class_id] }} · class {{ detection.class_id }} · score {{ detection.score }} · xyxy [{{ detection.xyxy.join(', ') }}]</li></ol><a :href="`/api/v1/artifacts/${encodeURIComponent(result.artifact_id)}/download`">下载结果 JSON</a>
      </article>
    </article>
    <p class="note">独立部署包仍未开放。单图成功不等于精度实验或边缘硬件验证。</p>
  </section>
</template>
<style scoped>
.inference-panel, .inference-panel label, .inference-panel select { min-width: 0; max-width: 100%; }
.inference-upload { display: flex; align-items: end; flex-wrap: wrap; gap: 12px; }
.inference-form { grid-template-columns: repeat(2, minmax(0, 1fr)); margin-top: 20px; }
.source-identity { display: grid; gap: 8px; } .source-identity dd { margin: 0; overflow-wrap: anywhere; }
.inference-jobs button, .identity, .job-log li, .detections li { overflow-wrap: anywhere; }
.inference-detail, .verified-inference { margin-top: 20px; }
.inference-preview { display: block; width: 100%; max-height: 640px; margin-block: 16px; background: #eef2f6; }
.inference-preview rect { fill: none; stroke: #c43b22; stroke-width: 2; vector-effect: non-scaling-stroke; }
@media (max-width: 760px) { .inference-form { grid-template-columns: minmax(0, 1fr); } }
</style>
