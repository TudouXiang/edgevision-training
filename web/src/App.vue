<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElButton, ElTag } from 'element-plus'
import {
  Activity, ArrowRight, ArrowUpRight, Boxes, ChevronRight, CircleDashed,
  Clock3, Database, FolderKanban, Info, Layers3, LogIn, Menu,
  PackageCheck, RefreshCw, ScanEye, Server, ShieldCheck, SlidersHorizontal, X,
} from '@lucide/vue'
import { checkSystem } from './api'
import type { Capabilities } from '../../contracts/api'

type StageKey = 'overview' | 'projects' | 'datasets' | 'training' | 'models' | 'onnx' | 'inference' | 'deployment'
type FeatureKey = keyof Capabilities['features']

const stages = [
  { key: 'projects', number: '01', title: '项目', icon: FolderKanban, feature: 'projects', line: '为一次检测目标建立独立工作空间。', requirement: '项目归属、成员权限与归档由服务端验证。', next: '创建项目 → 导入数据集' },
  { key: 'datasets', number: '02', title: '数据集', icon: Database, feature: 'datasets', line: '导入 YOLO 数据，并在训练前检查标签与划分。', requirement: '每次导入生成不可变快照和可下载的校验报告。', next: '校验通过 → 配置训练' },
  { key: 'training', number: '03', title: '训练', icon: SlidersHorizontal, feature: 'training_cpu', line: '选择 YOLO11n 与参数，提交到单机任务队列。', requirement: '每个任务有独立进程、持久状态、真实日志与指标。', next: '任务成功 → 登记模型' },
  { key: 'models', number: '04', title: '模型', icon: Boxes, feature: 'models', line: '追踪 best / last 权重、来源和文件指纹。', requirement: '未验证的模型不能标记为可部署。', next: '选择模型 → 导出 ONNX' },
  { key: 'onnx', number: '05', title: 'ONNX 导出', icon: Layers3, feature: 'onnx_export', line: '导出通用格式并在 CPU 运行时真实加载。', requirement: '保存导出参数、输入输出结构和一致性证据。', next: '验证通过 → 图片推理' },
  { key: 'inference', number: '06', title: '真实推理', icon: ScanEye, feature: 'onnx_inference', line: '用实际图片验证模型输出和后处理。', requirement: '保存输入哈希、阈值与推理结果，不显示模拟检测框。', next: '验证通过 → 生成部署包' },
  { key: 'deployment', number: '07', title: '部署包', icon: PackageCheck, feature: 'deployment', line: '下载模型、配置与可运行的单图示例。', requirement: '首版 ONNX 主线；RKNN 只保留扩展接口。', next: '校验清单 → 下载归档' },
] as const

const route = useRoute()
const router = useRouter()
const active = computed<StageKey>(() => (stages.some(stage => stage.key === route.params.stage) ? route.params.stage as StageKey : 'overview'))
const sidebarOpen = ref(false)
const checking = ref(true)
const live = ref(false)
const ready = ref(false)
const capabilities = ref<Capabilities | null>(null)
const checkedAt = ref('')
let request: AbortController | null = null

const selected = computed(() => stages.find(stage => stage.key === active.value))
const apiStatus = computed(() => checking.value ? '正在检查' : live.value ? 'API 已响应' : 'API 未连接')
const dbStatus = computed(() => checking.value ? '正在检查' : !live.value ? '状态未知' : ready.value ? '数据库已就绪' : '数据库未就绪')

async function refresh() {
  request?.abort()
  request = new AbortController()
  const signal = request.signal
  checking.value = true
  try {
    const response = await checkSystem(signal)
    if (signal.aborted) return
    live.value = response.live.status === 'ok'
    ready.value = response.ready?.status === 'ready'
    capabilities.value = response.capabilities
  } catch {
    if (signal.aborted) return
    live.value = false
    ready.value = false
    capabilities.value = null
  } finally {
    if (!signal.aborted) {
      checking.value = false
      checkedAt.value = new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(new Date())
    }
  }
}

function navigate(next: StageKey) {
  void router.push(next === 'overview' ? '/' : `/${next}`)
  sidebarOpen.value = false
  window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
}

function onKeyDown(event: KeyboardEvent) {
  if (event.key === 'Escape') sidebarOpen.value = false
}

onMounted(() => {
  refresh()
  window.addEventListener('keydown', onKeyDown)
})
onUnmounted(() => {
  request?.abort()
  window.removeEventListener('keydown', onKeyDown)
})
</script>

<template>
  <div class="app-shell">
    <a class="skip-link" href="#main-content">跳转到主要内容</a>
    <button v-if="sidebarOpen" class="mobile-scrim" type="button" aria-label="关闭导航菜单" @click="sidebarOpen = false" />

    <aside class="sidebar" :class="{ 'sidebar-open': sidebarOpen }" aria-label="工作区导航">
      <div class="brand-row">
        <div class="brand-mark" aria-hidden="true"><span /></div>
        <div class="brand-copy"><strong>YOLO<span> / </span>Workbench</strong><small>检测模型工作台</small></div>
        <button class="icon-button mobile-close" type="button" aria-label="关闭导航" @click="sidebarOpen = false"><X :size="19" /></button>
      </div>

      <div class="workspace-block">
        <span class="eyebrow">当前工作空间</span>
        <div class="workspace-select"><span class="workspace-icon"><CircleDashed :size="18" /></span><span>本地工作区<small>单机 · 目标检测</small></span><ChevronRight :size="16" class="muted-icon" /></div>
      </div>

      <nav class="side-nav" aria-label="平台页面">
        <span class="nav-label">工作台</span>
        <button class="nav-item" :class="{ active: active === 'overview' }" type="button" :aria-pressed="active === 'overview'" @click="navigate('overview')"><Activity :size="18" aria-hidden="true" /><span>总览</span></button>
        <span class="nav-label workflow-label">核心流程</span>
        <button v-for="stage in stages" :key="stage.key" class="nav-item" :class="{ active: active === stage.key }" type="button" :aria-pressed="active === stage.key" @click="navigate(stage.key)">
          <component :is="stage.icon" :size="18" aria-hidden="true" /><span>{{ stage.title }}</span><span class="nav-index">{{ stage.number }}</span>
        </button>
      </nav>

      <div class="sidebar-bottom">
        <div class="sidebar-note"><ShieldCheck :size="18" aria-hidden="true" /><p>所有实验结果都应来自真实任务和可追溯文件。</p></div>
        <div class="identity"><span class="identity-avatar"><LogIn :size="18" aria-hidden="true" /></span><span><strong>未登录</strong><small>账号功能待接入</small></span></div>
      </div>
    </aside>

    <div class="main-column">
      <header class="topbar">
        <div class="topbar-start">
          <button class="icon-button menu-toggle" type="button" aria-label="打开导航菜单" :aria-expanded="sidebarOpen" @click="sidebarOpen = true"><Menu :size="21" /></button>
          <span class="breadcrumb">本地工作区 <ChevronRight :size="15" aria-hidden="true" /> <strong>{{ selected?.title ?? '总览' }}</strong></span>
        </div>
        <div class="topbar-end">
          <span class="session-indicator"><span class="session-dot" /> 架构预览</span>
          <span class="topbar-divider" />
          <span class="topbar-account">访客模式</span>
        </div>
      </header>

      <main id="main-content" class="content" tabindex="-1">
        <div v-if="active === 'overview'" class="dashboard-view">
          <section class="hero" aria-labelledby="hero-title">
            <div class="hero-copy">
              <div class="hero-kicker"><span class="kicker-line" /> LOCAL VISION PLATFORM <span class="kicker-separator">/</span> ARCHITECTURE PREVIEW</div>
              <h1 id="hero-title">让每一次检测实验，<br /><em>都有迹可循。</em></h1>
              <p>从数据校验到训练、ONNX 验证和部署交付，沿着一条清晰的路径推进。现在展示的是产品骨架，业务流程仍在逐步接入。</p>
              <div class="hero-actions"><ElButton type="primary" disabled>创建第一个项目 <ArrowRight :size="16" aria-hidden="true" /></ElButton><span>登录与项目接口完成后开放</span></div>
            </div>
            <div class="hero-visual" aria-hidden="true"><span class="hero-orbit orbit-one" /><span class="hero-orbit orbit-two" /><span class="hero-crosshair" /><div class="hero-grid" /><span class="hero-visual-label">DETECT / TRACE / DEPLOY</span></div>
          </section>

          <section class="readiness-section" aria-labelledby="readiness-title">
            <div class="section-heading"><div><span class="eyebrow accent">SYSTEM STATUS</span><h2 id="readiness-title">环境与连接</h2><p>仅展示当前 API 的实际响应，不代表训练、导出或推理已可用。</p></div><button class="text-button" type="button" :disabled="checking" @click="refresh"><RefreshCw :size="16" :class="{ spinning: checking }" aria-hidden="true" /> 重新检查</button></div>
            <div class="status-grid" role="status" aria-live="polite">
              <article class="status-card"><div class="status-icon"><Server :size="20" aria-hidden="true" /></div><div><span>API 服务</span><strong>{{ apiStatus }}</strong><small>{{ checking ? '正在连接本机服务' : live ? '健康检查接口已响应' : '启动后可在此查看连接状态' }}</small></div><span class="status-light" :class="live ? 'positive' : checking ? 'pending' : 'negative'" /></article>
              <article class="status-card"><div class="status-icon"><Database :size="20" aria-hidden="true" /></div><div><span>数据库与文件</span><strong>{{ dbStatus }}</strong><small>{{ ready ? '已执行初始迁移' : '运行数据库迁移后才可就绪' }}</small></div><span class="status-light" :class="ready ? 'positive' : 'pending'" /></article>
              <article class="status-card"><div class="status-icon"><Clock3 :size="20" aria-hidden="true" /></div><div><span>最近检查</span><strong>{{ checkedAt || '尚未检查' }}</strong><small>按需刷新 · 无后台假心跳</small></div><span class="status-light neutral" /></article>
            </div>
          </section>

          <section class="progress-section" aria-labelledby="progress-title">
            <div class="section-heading"><div><span class="eyebrow accent">WORKFLOW</span><h2 id="progress-title">七步完成模型交付</h2><p>每一步都基于上一步的真实结果。点击查看功能边界和接入条件。</p></div><span class="section-meta">01 — 07</span></div>
            <div class="workflow-list">
              <button v-for="stage in stages" :key="stage.key" class="workflow-row" type="button" @click="navigate(stage.key)">
                <span class="workflow-number">{{ stage.number }}</span><span class="workflow-symbol"><component :is="stage.icon" :size="19" aria-hidden="true" /></span><span class="workflow-copy"><strong>{{ stage.title }}</strong><small>{{ stage.line }}</small></span><span class="workflow-state">待接入</span><ArrowUpRight :size="18" class="workflow-arrow" aria-hidden="true" />
              </button>
            </div>
          </section>

          <section class="bottom-grid" aria-label="交付边界">
            <article class="boundary-card"><div class="boundary-icon"><Info :size="19" aria-hidden="true" /></div><div><h3>关于当前版本</h3><p>这是一套已冻结接口与数据结构的可启动骨架。项目数量、训练曲线和模型指标须在真实业务完成后才会展示。</p></div></article>
            <article class="boundary-card muted-card"><div class="boundary-icon"><ShieldCheck :size="19" aria-hidden="true" /></div><div><h3>模型输出必须经过验证</h3><p>成功任务需要真实文件、哈希和验证记录；RKNN 目前仅有设计扩展位。</p></div></article>
          </section>
        </div>

        <div v-else-if="selected" class="detail-view">
          <div class="detail-heading"><span class="eyebrow accent">WORKFLOW / {{ selected.number }}</span><div class="detail-title-line"><div><h1>{{ selected.title }}</h1><p>{{ selected.line }}</p></div><ElTag effect="plain" type="info" round>尚未接入</ElTag></div></div>
          <section class="detail-canvas" :aria-label="`${selected.title}功能状态`">
            <span class="canvas-watermark">{{ selected.number }}</span>
            <div class="canvas-content"><span class="canvas-symbol"><component :is="selected.icon" :size="28" aria-hidden="true" /></span><span class="eyebrow accent">NEXT IN WORKFLOW</span><h2>{{ selected.title }}功能正在建设</h2><p>{{ selected.requirement }}</p><ElButton type="primary" disabled>开始{{ selected.title }} <ArrowRight :size="16" aria-hidden="true" /></ElButton><small>服务端功能完成并通过验收后开放操作</small></div>
          </section>
          <div class="detail-footer"><div><span>当前能力</span><strong>{{ capabilities?.features[selected.feature as FeatureKey]?.available ? '接口已报告可用 · 页面待接入' : '尚未实现' }}</strong></div><div><span>下一步</span><strong>{{ selected.next }}</strong></div><div><span>验收要求</span><strong>实际命令 · 文件指纹 · 真实输出</strong></div></div>
          <button class="back-button" type="button" @click="navigate('overview')"><ArrowRight :size="16" aria-hidden="true" /> 返回总览</button>
        </div>
      </main>

      <footer class="footer"><span>YOLO Workbench <span class="footer-sep">/</span> 单机目标检测平台</span><span>架构骨架 · 业务功能未验收</span></footer>
    </div>
  </div>
</template>
