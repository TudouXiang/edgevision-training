<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ApiClientError, jobApi } from '../api'
import type { Project, Dataset, Capabilities, TrainParams, Job, Metric, Artifact } from '../api'
const props = defineProps<{project: Project; datasets: Dataset[]; capability?: Capabilities['features'][string]}>()
const emit = defineEmits<{error: [value: unknown]}>()
const ready = computed(() => props.datasets.filter(value => value.state === 'ready'))
const dataset = ref(''), name = ref('检测实验'), epochs = ref(1), batch = ref(1), imgsz = ref<320 | 640>(320), seed = ref(0), lr = ref(.01)
const jobs = ref<Job[]>([]), chosen = ref<Job | null>(null), metrics = ref<Metric[]>([]), artifacts = ref<Artifact[]>([])
const warning = ref(''), submitting = ref(false), cancelling = ref(false), done = ref(false)
const page = ref(1), total = ref(0)
const controller = new AbortController()
let timer: ReturnType<typeof setTimeout> | undefined
let cursor: string | null = null, revision = 0, busy = false, delay = 2000
let pending: {body: string; key: string} | null = null
const terminal = (job: Job) => ['succeeded', 'failed', 'cancelled', 'interrupted'].includes(job.state)
const series = computed(() => [...new Set(metrics.value.map(value => value.name))].map(name => ({name, values: metrics.value.filter(value => value.name === name)})))
function points(values: Metric[]) {
  const low = Math.min(...values.map(value => value.value)), high = Math.max(...values.map(value => value.value))
  const maxEpoch = Math.max(2, ...values.map(value => value.epoch))
  return values.map(value => `${10 + (value.epoch - 1) / (maxEpoch - 1) * 280},${75 - (value.value - low) / (high - low || 1) * 60}`).join(' ')
}
function error(value: unknown) {
  if (controller.signal.aborted || value instanceof DOMException && value.name === 'AbortError') return
  warning.value = value instanceof Error ? value.message : '训练状态暂时无法读取，将重试。'
  if (value instanceof ApiClientError && value.status === 401) emit('error', value)
}
function choose(job: Job) { revision++; chosen.value = job; metrics.value = []; artifacts.value = []; cursor = null; done.value = false; void poll() }
async function poll() {
  if (busy || controller.signal.aborted) return
  busy = true
  const expected = revision
  let succeeded = false
  try {
    const result = await jobApi.list(props.project.id, controller.signal, page.value)
    if (expected !== revision || controller.signal.aborted) return
    jobs.value = result.items.filter(job => job.kind === 'train'); total.value = result.total
    if (!chosen.value && jobs.value[0]) { chosen.value = jobs.value[0]; done.value = false }
    const id = chosen.value?.id
    if (id) {
      const detail = await jobApi.detail(id, controller.signal)
      if (expected !== revision || controller.signal.aborted) return
      chosen.value = detail
      if (!done.value) {
        const result = await jobApi.metrics(id, cursor, controller.signal)
        if (expected !== revision || controller.signal.aborted) return
        const last = metrics.value.at(-1)?.seq ?? 0
        metrics.value = [...metrics.value, ...result.items.filter(value => value.seq > last)].slice(-1000)
        cursor = result.next_cursor; done.value = result.eof
      }
      if (detail.state === 'succeeded') {
        let all: Artifact[] = [], next = 1
        while (next <= 100) {
          const result = await jobApi.artifacts(props.project.id, controller.signal, next++)
          all = [...all, ...result.items]
          if (all.length >= result.total) break
        }
        if (expected !== revision || controller.signal.aborted) return
        artifacts.value = all.filter(value => value.job_id === id && ['pt_best', 'pt_last'].includes(value.kind))
      }
    }
    warning.value = ''; delay = 2000; succeeded = true
  } catch (value) { if (expected === revision) { error(value); delay = Math.min(delay * 2, 15000) } }
  finally {
    busy = false
    if (!controller.signal.aborted) { clearTimeout(timer); timer = setTimeout(() => void poll(), succeeded && chosen.value && terminal(chosen.value) && !done.value ? 100 : delay) }
  }
}
async function submit(source?: string) {
  if (submitting.value || props.project.archived_at || !props.capability?.available) return
  const params: TrainParams = {dataset_id: dataset.value, experiment_name: name.value, epochs: epochs.value, batch: batch.value, imgsz: imgsz.value, seed: seed.value, learning_rate: lr.value, base_model: 'yolo11n.pt', device: 'cpu'}
  const body = JSON.stringify({params, source})
  if (!pending || pending.body !== body) pending = {body, key: crypto.randomUUID()}
  submitting.value = true
  const expected = ++revision
  try {
    const accepted = await jobApi.train(props.project.id, params, pending.key, controller.signal, source)
    if (controller.signal.aborted || revision !== expected) return
    const detail = await jobApi.detail(accepted.job_id, controller.signal)
    if (controller.signal.aborted || revision !== expected) return
    pending = null
    page.value = 1; choose(detail)
  } catch (value) { if (revision === expected) error(value) }
  finally { if (!controller.signal.aborted) submitting.value = false }
}
async function cancel() {
  if (!chosen.value || cancelling.value || terminal(chosen.value)) return
  cancelling.value = true
  const id = chosen.value.id
  const expected = ++revision
  try { const result = await jobApi.cancel(id, controller.signal); if (!controller.signal.aborted && chosen.value?.id === id && revision === expected) chosen.value = result }
  catch (value) { if (revision === expected) error(value) }
  finally { if (!controller.signal.aborted) cancelling.value = false }
}
function changePage(next: number) {
  if (next < 1 || next > Math.max(1, Math.ceil(total.value / 20))) return
  revision++; page.value = next; chosen.value = null; metrics.value = []; artifacts.value = []; cursor = null; done.value = false
  void poll()
}
function retry() {
  const previous = chosen.value?.training?.params
  if (!previous || !chosen.value) return
  dataset.value = previous.dataset_id; name.value = previous.experiment_name; epochs.value = previous.epochs; batch.value = previous.batch
  imgsz.value = previous.imgsz ?? 640; seed.value = previous.seed; lr.value = previous.learning_rate ?? .01
  void submit(chosen.value.id)
}
onMounted(() => void poll())
onUnmounted(() => { controller.abort(); clearTimeout(timer); revision++ })
</script>
<template>
  <section class="panel training-panel" aria-label="真实 YOLO 训练">
    <h2>YOLO11n 训练</h2>
    <p class="note">仅目标检测 · CPU · 全局单重任务队列。指标来自真实轮次回调，PT 验证不代表精度达标或 ONNX 可用。</p>
    <p v-if="!capability?.available" class="note">{{ capability?.reason ?? '训练环境尚未验证。' }}</p>
    <p v-if="project.archived_at" class="note">归档项目不能创建训练。</p>
    <p v-if="warning" role="alert" class="error">{{ warning }}</p>
    <form class="grid-form" @submit.prevent="submit()">
      <label>训练数据集<select v-model="dataset" required><option value="">选择 ready 快照</option><option v-for="item in ready" :key="item.id" :value="item.id">{{ item.name }} · v{{ item.version }}</option></select></label>
      <label>实验名称<input v-model="name" required maxlength="160" /></label>
      <label>训练轮数<input v-model.number="epochs" type="number" required min="1" max="100" /></label>
      <label>批量大小<input v-model.number="batch" type="number" required min="1" max="16" /></label>
      <label>图像尺寸<select v-model.number="imgsz"><option :value="320">320</option><option :value="640">640</option></select></label>
      <label>随机种子<input v-model.number="seed" type="number" required min="0" max="4294967295" /></label>
      <label>初始学习率<input v-model.number="lr" type="number" required min="0.000001" max="0.1" step="any" /></label>
      <button class="primary" :disabled="submitting || !dataset || !capability?.available || Boolean(project.archived_at)">{{ submitting ? '正在提交…' : '创建训练任务' }}</button>
    </form>
    <p v-if="!jobs.length" class="note">当前页没有训练任务。没有模拟进度或指标。</p>
    <div class="actions"><button v-for="job in jobs" :key="job.id" @click="choose(job)">{{ job.training?.params.experiment_name ?? job.id.slice(0, 8) }} · {{ job.state }}</button></div>
    <div v-if="total > 20" class="actions"><button :disabled="page <= 1" @click="changePage(page - 1)">上一页</button><span>{{ page }}</span><button :disabled="page * 20 >= total" @click="changePage(page + 1)">下一页</button></div>
    <article v-if="chosen" class="training-detail">
      <h3>{{ chosen.training?.params.experiment_name }} · {{ chosen.state }}</h3>
      <p v-if="chosen.error_code" role="status">{{ chosen.error_code }}</p>
      <div class="actions"><button :disabled="terminal(chosen) || chosen.state === 'cancelling' || cancelling" @click="cancel">取消训练</button><button :disabled="!terminal(chosen) || submitting || !capability?.available || Boolean(project.archived_at)" @click="retry">重新训练（新任务）</button></div>
      <p v-if="!metrics.length" class="note">暂无真实指标。</p>
      <p v-else class="note">已完成 {{ Math.max(...metrics.map(value => value.epoch)) }} / {{ chosen.training?.params.epochs }} 轮 · {{ done ? '最终指标已读取' : '持续读取指标' }}</p>
      <div class="metric-grid"><figure v-for="item in series" :key="item.name"><figcaption>{{ item.name }} · 最新 {{ item.values.at(-1)?.value.toPrecision(5) }}</figcaption><svg viewBox="0 0 300 90" role="img" :aria-label="`${item.name} 真实指标曲线`"><polyline :points="points(item.values)" fill="none" stroke="currentColor" stroke-width="2" /></svg><small>{{ item.values.map(value => `第 ${value.epoch} 轮: ${value.value.toPrecision(5)}`).join('；') }}</small></figure></div>
      <div class="actions"><a v-for="item in artifacts" :key="item.id" :href="`/api/v1/artifacts/${item.id}/download`">下载 {{ item.kind }}（{{ item.size_bytes.toLocaleString() }} bytes）</a></div>
      <details v-if="chosen.training"><summary>输入与环境追溯</summary><dl><dt>数据版本</dt><dd>{{ chosen.training.dataset_id }} · {{ chosen.training.dataset_version }}</dd><dt>数据摘要</dt><dd>{{ chosen.training.snapshot_sha256 }}</dd><dt>基础权重清单摘要</dt><dd>{{ chosen.training.base_manifest_sha256 }}</dd><dt>环境指纹</dt><dd>{{ chosen.training.runtime_binding }}</dd><dt>代码指纹</dt><dd>{{ chosen.training.code_version }}</dd><dt>类别</dt><dd>{{ chosen.training.classes.join('、') }}</dd></dl></details>
    </article>
  </section>
</template>
<style scoped>
.metric-grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); gap: 12px; }
figure { margin: 0; padding: 12px; background: #f3f6fa; border-radius: 12px; }
figure svg { width: 100%; color: #3560b5; }
figure small { overflow-wrap: anywhere; }
dl { display: grid; gap: 8px; } dd { margin: 0; overflow-wrap: anywhere; }
.training-detail { margin-top: 20px; }
</style>
