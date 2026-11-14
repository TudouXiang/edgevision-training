<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { adminApi, ApiClientError, jobApi } from '../api'
import type { Job, JobLog } from '../api'
const emit = defineEmits<{ error: [value: unknown] }>()
const jobs = ref<Job[]>([])
const page = ref(1)
const total = ref(0)
const loading = ref(false)
const warning = ref('')
const selected = ref<Job | null>(null)
const lines = ref<JobLog[]>([])
const detailLoading = ref(false)
const logLoading = ref(false)
const logDone = ref(false)
const cancelling = ref(false)
const notice = ref('')
const controller = new AbortController()
let listRevision = 0
let detailRevision = 0
let cursor: string | null = null
const active = () => !controller.signal.aborted
const cancellable = (j: Job) => ['queued', 'running'].includes(j.state)
function error(value: unknown, message: string) {
  if (!active() || (value instanceof DOMException && value.name === 'AbortError')) return
  warning.value = value instanceof ApiClientError ? `${message} ${value.message}` : message
  if (value instanceof ApiClientError && value.status === 401) emit('error', value)
}
async function refresh(target = page.value) {
  const revision = ++listRevision
  loading.value = true
  try {
    const result = await adminApi.jobs(target, 20, controller.signal)
    if (!active() || revision !== listRevision) return
    jobs.value = result.items; page.value = result.page; total.value = result.total; warning.value = ''
  } catch (e) { if (revision === listRevision) error(e, '任务列表尚未刷新，当前内容可能已过期。请重试。') }
  finally { if (active() && revision === listRevision) loading.value = false }
}
async function readLogs() {
  const id = selected.value?.id
  const revision = detailRevision
  if (!id || logLoading.value || logDone.value) return
  logLoading.value = true
  try {
    const result = await jobApi.logs(id, cursor, controller.signal)
    if (!active() || revision !== detailRevision) return
    const last = lines.value.at(-1)?.seq ?? 0
    lines.value = [...lines.value, ...result.items.filter(x => x.seq > last)].slice(-500)
    cursor = result.next_cursor; logDone.value = result.eof
  } catch (e) { if (revision === detailRevision) error(e, '日志读取失败，请重试。') }
  finally { if (active() && revision === detailRevision) logLoading.value = false }
}
async function choose(id: string) {
  const revision = ++detailRevision
  selected.value = null; lines.value = []; cursor = null; logDone.value = false
  logLoading.value = false; detailLoading.value = true; notice.value = ''
  try {
    const result = await jobApi.detail(id, controller.signal)
    if (!active() || revision !== detailRevision) return
    selected.value = result; warning.value = ''; await readLogs()
  } catch (e) { if (revision === detailRevision) error(e, '任务详情读取失败，请重试。') }
  finally { if (active() && revision === detailRevision) detailLoading.value = false }
}
function close() { ++detailRevision; selected.value = null; detailLoading.value = false; logLoading.value = false; lines.value = []; notice.value = '' }
async function cancel() {
  const task = selected.value
  const revision = detailRevision
  if (!task || !cancellable(task) || cancelling.value) return
  cancelling.value = true
  try {
    const result = await jobApi.cancel(task.id, controller.signal)
    if (!active()) return
    jobs.value = jobs.value.map(j => j.id === result.id ? result : j)
    if (revision === detailRevision) {
      selected.value = result; warning.value = ''
      notice.value = result.state === 'cancelling' ? '取消请求已接收，仍需等待受管进程退出。请刷新详情确认最终状态。' : '已返回服务端当前状态。'
    }
  } catch (e) { if (revision === detailRevision) error(e, '取消结果未确认，请刷新详情或重试。') }
  finally { if (active()) cancelling.value = false }
}
onMounted(() => { void refresh() })
onUnmounted(() => { controller.abort(); ++listRevision; ++detailRevision })
</script>

<template>
  <section class="panel admin-jobs" aria-label="管理员全局任务">
    <div class="section-title"><h2>全局任务</h2><button :disabled="loading" @click="refresh()">刷新任务</button></div>
    <p class="note">跨项目的真实任务快照；状态变化后请刷新。每页最多 20 项，不是实时资源监控。</p>
    <p v-if="warning" role="alert">{{ warning }}</p>
    <p v-if="loading" role="status">正在读取任务…</p>
    <p v-if="!loading && !warning && !jobs.length" class="empty">当前页没有任务。</p>
    <article v-for="job in jobs" :key="job.id" class="row-card">
      <div><strong>{{ job.kind }} · {{ job.state }}</strong><p>任务 {{ job.id }}</p><small>项目 {{ job.project_id }}</small></div>
      <button data-detail @click="choose(job.id)">查看</button>
    </article>
    <div class="actions"><button :disabled="loading || page <= 1" @click="refresh(page - 1)">上一页</button><span>第 {{ page }} 页 · 共 {{ total }} 项</span><button :disabled="loading || page * 20 >= total" @click="refresh(page + 1)">下一页</button></div>
    <p v-if="detailLoading" role="status">正在读取详情…</p>
    <section v-if="selected" aria-label="全局任务详情">
      <h3>{{ selected.kind }} · {{ selected.state }}</h3><p>{{ selected.id }}</p>
      <p v-if="selected.error_code">错误码：{{ selected.error_code }}</p>
      <div class="actions"><button @click="choose(selected.id)">刷新详情</button><button v-if="cancellable(selected)" :disabled="cancelling" @click="cancel">请求取消</button><button @click="close">关闭详情</button></div>
      <p v-if="notice" role="status">{{ notice }}</p>
      <p class="note">最多保留最近 500 行；日志与状态分别读取，日志末尾不代表任务终态。</p>
      <pre aria-label="全局任务日志">{{ lines.map(line => line.text).join('\n') }}</pre>
      <button v-if="!logDone" :disabled="logLoading" @click="readLogs">读取后续日志</button><p v-else>当前日志已读取完毕。</p>
    </section>
  </section>
</template>
<style scoped>
.admin-jobs p,.admin-jobs small { overflow-wrap:anywhere }
.admin-jobs pre { white-space:pre-wrap; overflow-wrap:anywhere; max-height:20rem; overflow:auto }
.admin-jobs .row-card>div { min-width:0 }
</style>
