<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { ApiClientError, datasetApi, jobApi } from '../api'
import type { Dataset, Job, JobLog } from '../api'

const props = defineProps<{ projectId: string; datasets: Dataset[] }>()
const emit = defineEmits<{ dataset: [value: Dataset]; error: [value: unknown] }>()
const jobs = ref<Job[]>([])
const page = ref(1)
const total = ref(0)
const selected = ref<string | null>(null)
const lines = ref<JobLog[]>([])
const submitting = ref<string | null>(null)
const cancelling = ref<string | null>(null)
const loading = ref(false)
const warning = ref('')
const logDone = ref(false)
const keys = new Map<string, string>()
const controller = new AbortController()
let timer: ReturnType<typeof setTimeout> | undefined
let cursor: string | null = null
let logRevision = 0
let polling = false
let logLoading = false
let selectionInitialized = false
let revision = 0
let delay = 2000
const terminal = (state: Job['state']) => ['succeeded', 'failed', 'cancelled', 'interrupted'].includes(state)
const current = () => !controller.signal.aborted

function error(value: unknown) {
  if (!current() || (value instanceof DOMException && value.name === 'AbortError')) return
  warning.value = value instanceof ApiClientError ? value.message : '任务状态暂时无法读取，将自动重试。'
  if (value instanceof ApiClientError && value.status === 401) emit('error', value)
}

async function refreshDatasets() {
  const expected = revision
  for (const dataset of props.datasets) {
    if (dataset.state !== 'validating' && dataset.id !== submitting.value) continue
    const updated = await datasetApi.detail(dataset.id, controller.signal)
    if (current() && expected === revision) emit('dataset', updated)
  }
}

async function readLogs() {
  const id = selected.value
  const expected = logRevision
  if (!id || logDone.value || logLoading) return
  logLoading = true
  try {
    const result = await jobApi.logs(id, cursor, controller.signal)
    if (!current() || selected.value !== id || expected !== logRevision) return
    const last = lines.value.at(-1)?.seq ?? 0
    lines.value = [...lines.value, ...result.items.filter(line => line.seq > last)].slice(-500)
    cursor = result.next_cursor
    logDone.value = result.eof
    const existing = jobs.value.find(job => job.id === id)
    if (existing) existing.state = result.job_state
  } finally { logLoading = false }
}

function schedule(milliseconds = delay) {
  clearTimeout(timer)
  if (current()) timer = setTimeout(() => { void poll() }, milliseconds)
}

async function poll() {
  if (!current() || polling) return
  polling = true
  loading.value = true
  try {
    const expected = revision
    const result = await jobApi.list(props.projectId, controller.signal, page.value)
    if (!current() || expected !== revision) return
    jobs.value = result.items
    total.value = result.total
    if (!selectionInitialized && jobs.value.length) select(jobs.value[0].id, false)
    await refreshDatasets()
    await readLogs() // Always read again after seeing terminal, until server eof.
    warning.value = ''
    delay = 2000
  } catch (value) { error(value); delay = Math.min(delay * 2, 15000) }
  finally {
    polling = false
    if (current()) {
      loading.value = false
      schedule(terminal(jobs.value.find(job => job.id === selected.value)?.state ?? 'queued') && !logDone.value ? 100 : delay)
    }
  }
}

function select(id: string, fetchNow = true) {
  selectionInitialized = true
  logRevision += 1
  selected.value = id
  cursor = null
  lines.value = []
  logDone.value = false
  if (fetchNow) void readLogs().catch(error)
}

function changePage(next: number) {
  if (next < 1 || next > Math.max(1, Math.ceil(total.value / 20))) return
  revision += 1
  page.value = next
  closeLogs()
  selectionInitialized = false
  void poll()
}

function closeLogs() {
  selectionInitialized = true
  logRevision += 1
  selected.value = null
  lines.value = []
  cursor = null
  logDone.value = true
}

async function checkDataset(dataset: Dataset) {
  if (!current() || submitting.value) return
  revision += 1
  page.value = 1
  submitting.value = dataset.id
  warning.value = ''
  const key = keys.get(dataset.id) ?? crypto.randomUUID()
  keys.set(dataset.id, key) // Retain the same key if the response is lost.
  try {
    const accepted = await datasetApi.check(dataset.id, key, controller.signal)
    if (!current()) return
    keys.delete(dataset.id)
    select(accepted.job_id, false)
    const updated = await datasetApi.detail(dataset.id, controller.signal)
    if (!current()) return
    emit('dataset', updated)
    await poll()
  } catch (value) { error(value) }
  finally { if (current()) submitting.value = null }
}

async function cancel(job: Job) {
  if (cancelling.value || terminal(job.state)) return
  revision += 1
  cancelling.value = job.id
  try {
    const updated = await jobApi.cancel(job.id, controller.signal)
    if (!current()) return
    jobs.value = jobs.value.map(item => item.id === job.id ? updated : item)
    await refreshDatasets()
    await readLogs()
  } catch (value) { error(value) }
  finally { if (current()) cancelling.value = null }
}

defineExpose({ checkDataset, submitting })
onMounted(() => { void poll() })
onUnmounted(() => { controller.abort(); clearTimeout(timer); logRevision += 1 })
</script>

<template>
  <section class="job-panel" aria-label="校验任务">
    <div class="section-title"><h3>校验任务</h3><span>全局单任务顺序执行</span><button :disabled="loading" @click="poll">刷新任务</button></div>
    <p v-if="warning" class="error" role="alert">{{ warning }}</p>
    <p v-if="!jobs.length" class="note">尚无校验任务。上传后点击“开始校验”。</p>
    <article v-for="job in jobs" :key="job.id" class="job-row">
      <div><strong>{{ job.kind }}</strong><span :class="job.state">{{ job.state }}</span><small>{{ job.id.slice(0, 8) }} · {{ job.error_code ?? (job.state === 'queued' ? '等待 Worker 领取' : '真实任务状态') }}</small></div>
      <div class="actions"><button @click="select(job.id)">查看日志</button><button :disabled="terminal(job.state) || job.state === 'cancelling' || cancelling === job.id" @click="cancel(job)">{{ job.state === 'cancelling' ? '正在停止…' : '取消任务' }}</button></div>
    </article>
    <div v-if="total > 20" class="actions job-pagination"><button :disabled="page === 1 || loading" @click="changePage(page - 1)">上一页任务</button><span>第 {{ page }} / {{ Math.ceil(total / 20) }} 页 · 共 {{ total }} 条</span><button :disabled="page * 20 >= total || loading" @click="changePage(page + 1)">下一页任务</button></div>
    <div v-if="selected" class="job-log" role="region" aria-label="任务日志">
      <div class="section-title"><strong>任务日志 · {{ selected.slice(0, 8) }}</strong><button @click="closeLogs">关闭日志</button></div>
      <p v-if="!lines.length" class="note">暂无日志，未合成进度或指标。</p>
      <ol><li v-for="line in lines" :key="line.seq"><span>{{ line.level }}</span> {{ line.text }}</li></ol>
      <small>{{ logDone ? '已读取最终日志' : '增量读取中' }} · 页面最多保留最近 500 行</small>
    </div>
  </section>
</template>
