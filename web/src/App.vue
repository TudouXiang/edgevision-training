<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Activity, Archive, Database, FolderPlus, Images, LogOut, Pencil, RefreshCw, ShieldCheck, UploadCloud, UserPlus } from '@lucide/vue'
import { adminApi, ApiClientError, authApi, checkSystem, datasetApi, projectApi } from './api'
import type { Capabilities, Dataset, DatasetSample, Project, User } from './api'

const PAGE_SIZE = 20
const booting = ref(true)
const user = ref<User | null>(null)
const projects = ref<Project[]>([])
const projectTotal = ref(0)
const projectPage = ref(1)
const users = ref<User[]>([])
const userTotal = ref(0)
const userPage = ref(1)
const globalError = ref('')
const username = ref('')
const password = ref('')
const signingIn = ref(false)
const signingOut = ref(false)
const projectName = ref('')
const projectDescription = ref('')
const creatingProject = ref(false)
const refreshingProjects = ref(false)
const loadingMoreProjects = ref(false)
const projectBusy = ref<string | null>(null)
const editingProject = ref<string | null>(null)
const editName = ref('')
const editDescription = ref('')
const newUsername = ref('')
const newPassword = ref('')
const newRole = ref<'user' | 'admin'>('user')
const creatingUser = ref(false)
const loadingMoreUsers = ref(false)
const userBusy = ref<string | null>(null)
const currentPassword = ref('')
const replacementPassword = ref('')
const changingPassword = ref(false)
const accountMessage = ref('')
const selectedProjectId = ref('')
const datasets = ref<Dataset[]>([])
const datasetTotal = ref(0)
const datasetPage = ref(1)
const datasetFile = ref<File | null>(null)
const datasetInput = ref<HTMLInputElement | null>(null)
const loadingDatasets = ref(false)
const loadingMoreDatasets = ref(false)
const uploadingDataset = ref(false)
const previewingDataset = ref<string | null>(null)
const previewSamples = ref<DatasetSample[]>([])
const previewLoading = ref(false)
const checkingSystem = ref(true)
const apiLive = ref(false)
const apiReady = ref(false)
const capabilities = ref<Capabilities | null>(null)
const isAdmin = computed(() => user.value?.role === 'admin')
const selectedProject = computed(() => projects.value.find(project => project.id === selectedProjectId.value) ?? null)
const stages = computed(() => [
  ['身份', capabilities.value?.features.auth?.available],
  ['项目', capabilities.value?.features.projects?.available],
  ['数据集', capabilities.value?.features.datasets?.available],
  ['训练', capabilities.value?.features.training_cpu?.available],
  ['ONNX', capabilities.value?.features.onnx_export?.available],
  ['推理', capabilities.value?.features.onnx_inference?.available],
  ['部署', capabilities.value?.features.deployment?.available],
] as const)

let generation = 0
let projectRevision = 0
let userRevision = 0
let datasetRevision = 0
let datasetReadRevision = 0
let sessionController: AbortController | null = null
let systemController: AbortController | null = null
let datasetController: AbortController | null = null

function message(error: unknown): string {
  if (error instanceof ApiClientError) return error.message
  return '无法连接 API，请稍后重试。'
}

function isAbort(error: unknown) { return error instanceof DOMException && error.name === 'AbortError' }
function isCurrent(value: number) { return value === generation && Boolean(user.value) && !sessionController?.signal.aborted }

function resetSessionDrafts() {
  username.value = ''
  password.value = ''
  projectName.value = ''
  projectDescription.value = ''
  editingProject.value = null
  editName.value = ''
  editDescription.value = ''
  newUsername.value = ''
  newPassword.value = ''
  newRole.value = 'user'
  currentPassword.value = ''
  replacementPassword.value = ''
  accountMessage.value = ''
  selectedProjectId.value = ''
  datasets.value = []
  datasetTotal.value = 0
  datasetPage.value = 1
  datasetFile.value = null
  if (datasetInput.value) datasetInput.value.value = ''
  loadingDatasets.value = false
  loadingMoreDatasets.value = false
  uploadingDataset.value = false
  previewingDataset.value = null
  previewSamples.value = []
  previewLoading.value = false
  projectBusy.value = null
  userBusy.value = null
  creatingProject.value = false
  creatingUser.value = false
  changingPassword.value = false
  refreshingProjects.value = false
  loadingMoreProjects.value = false
  loadingMoreUsers.value = false
}

function invalidateSession() {
  generation += 1
  projectRevision += 1
  userRevision += 1
  datasetRevision += 1
  datasetReadRevision += 1
  sessionController?.abort()
  datasetController?.abort()
  datasetController = null
  sessionController = null
  user.value = null
  projects.value = []
  projectTotal.value = 0
  projectPage.value = 1
  users.value = []
  userTotal.value = 0
  userPage.value = 1
  resetSessionDrafts()
}

function startSession(next: User): number {
  invalidateSession()
  user.value = next
  sessionController = new AbortController()
  return generation
}

function handleError(error: unknown, expected = generation) {
  if (expected !== generation) return
  if (isAbort(error)) return
  if (error instanceof ApiClientError && error.status === 401) invalidateSession()
  globalError.value = message(error)
}

async function refreshSystem() {
  systemController?.abort()
  const controller = new AbortController()
  systemController = controller
  checkingSystem.value = true
  try {
    const result = await checkSystem(controller.signal)
    apiLive.value = result.live.status === 'ok'
    apiReady.value = result.ready?.status === 'ready'
    capabilities.value = result.capabilities
  } catch (error) {
    if (!isAbort(error)) { apiLive.value = false; apiReady.value = false; capabilities.value = null }
  } finally { if (!controller.signal.aborted && systemController === controller) checkingSystem.value = false }
}

async function loadWorkspace(expected = generation) {
  if (!isCurrent(expected) || !sessionController) return
  const signal = sessionController.signal
  const admin = user.value?.role === 'admin'
  const expectedProjects = ++projectRevision
  const expectedUsers = ++userRevision
  loadingMoreProjects.value = false
  loadingMoreUsers.value = false
  const [projectResult, userResult] = await Promise.all([
    projectApi.list(1, PAGE_SIZE, signal),
    admin ? adminApi.users(1, PAGE_SIZE, signal) : Promise.resolve(null),
  ])
  if (!isCurrent(expected) || expectedProjects !== projectRevision || expectedUsers !== userRevision) return
  projects.value = projectResult.items
  projectTotal.value = projectResult.total
  projectPage.value = 1
  users.value = userResult?.items ?? []
  userTotal.value = userResult?.total ?? 0
  userPage.value = 1
}

async function bootstrap() {
  booting.value = true
  globalError.value = ''
  const controller = new AbortController()
  try {
    const current = await authApi.me(controller.signal)
    const expected = startSession(current)
    await loadWorkspace(expected)
  } catch (error) {
    if (!(error instanceof ApiClientError && error.status === 401) && !isAbort(error)) globalError.value = message(error)
    invalidateSession()
  } finally { booting.value = false }
}

async function signIn() {
  if (signingIn.value || signingOut.value) return
  signingIn.value = true
  globalError.value = ''
  try {
    const current = await authApi.login({ username: username.value, password: password.value })
    const expected = startSession(current)
    await loadWorkspace(expected)
  } catch (error) {
    invalidateSession()
    if (!isAbort(error)) globalError.value = message(error)
  } finally { signingIn.value = false }
}

async function signOut() {
  if (signingOut.value) return
  signingOut.value = true
  globalError.value = ''
  const request = authApi.logout()
  invalidateSession() // Invalidate all earlier responses before awaiting the network.
  try { await request }
  catch (error) { globalError.value = `服务器退出失败，会话可能仍有效。${message(error)}` }
  finally { signingOut.value = false }
}

async function refreshProjects() {
  if (refreshingProjects.value || !sessionController) return
  const expected = generation
  const expectedRevision = ++projectRevision
  loadingMoreProjects.value = false
  refreshingProjects.value = true
  try {
    const result = await projectApi.list(1, PAGE_SIZE, sessionController.signal)
    if (isCurrent(expected) && expectedRevision === projectRevision) {
      projects.value = result.items; projectTotal.value = result.total; projectPage.value = 1
      if (selectedProjectId.value && !projects.value.some(project => project.id === selectedProjectId.value)) clearDatasetSelection()
    }
  } catch (error) { if (expectedRevision === projectRevision) handleError(error, expected) }
  finally { if (expected === generation) refreshingProjects.value = false }
}

async function loadMoreProjects() {
  if (loadingMoreProjects.value || projects.value.length >= projectTotal.value || !sessionController) return
  const expected = generation
  const expectedRevision = projectRevision
  loadingMoreProjects.value = true
  const next = projectPage.value + 1
  try {
    const result = await projectApi.list(next, PAGE_SIZE, sessionController.signal)
    if (isCurrent(expected) && expectedRevision === projectRevision) { projects.value.push(...result.items); projectTotal.value = result.total; projectPage.value = next }
  } catch (error) { if (expectedRevision === projectRevision) handleError(error, expected) }
  finally { if (expected === generation) loadingMoreProjects.value = false }
}

async function refreshUsers() {
  if (!sessionController) return
  const expected = generation
  const expectedRevision = ++userRevision
  loadingMoreUsers.value = false
  const result = await adminApi.users(1, PAGE_SIZE, sessionController.signal)
  if (isCurrent(expected) && expectedRevision === userRevision) { users.value = result.items; userTotal.value = result.total; userPage.value = 1 }
}

async function loadMoreUsers() {
  if (loadingMoreUsers.value || users.value.length >= userTotal.value || !sessionController) return
  const expected = generation
  const expectedRevision = userRevision
  loadingMoreUsers.value = true
  const next = userPage.value + 1
  try {
    const result = await adminApi.users(next, PAGE_SIZE, sessionController.signal)
    if (isCurrent(expected) && expectedRevision === userRevision) { users.value.push(...result.items); userTotal.value = result.total; userPage.value = next }
  } catch (error) { if (expectedRevision === userRevision) handleError(error, expected) }
  finally { if (expected === generation) loadingMoreUsers.value = false }
}

async function createProject() {
  if (creatingProject.value || !sessionController) return
  const expected = generation
  creatingProject.value = true
  globalError.value = ''
  try {
    await projectApi.create({ name: projectName.value, description: projectDescription.value }, sessionController.signal)
    if (!isCurrent(expected)) return
    projectName.value = ''; projectDescription.value = ''
    await refreshProjects()
  } catch (error) { handleError(error, expected) }
  finally { if (expected === generation) creatingProject.value = false }
}

function startEdit(project: Project) { editingProject.value = project.id; editName.value = project.name; editDescription.value = project.description }

async function saveProject(project: Project) {
  if (projectBusy.value || !sessionController) return
  const expected = generation
  projectBusy.value = project.id
  try {
    await projectApi.update(project.id, { name: editName.value, description: editDescription.value }, sessionController.signal)
    if (isCurrent(expected)) { editingProject.value = null; await refreshProjects() }
  } catch (error) { handleError(error, expected) }
  finally { if (expected === generation) projectBusy.value = null }
}

async function archiveProject(project: Project) {
  if (projectBusy.value || project.archived_at || !sessionController) return
  const expected = generation
  projectBusy.value = project.id
  try { await projectApi.archive(project.id, sessionController.signal); if (isCurrent(expected)) await refreshProjects() }
  catch (error) { handleError(error, expected) }
  finally { if (expected === generation) projectBusy.value = null }
}

function clearDatasetSelection() {
  datasetRevision += 1
  datasetReadRevision += 1
  datasetController?.abort()
  datasetController = null
  selectedProjectId.value = ''
  datasets.value = []
  datasetTotal.value = 0
  datasetPage.value = 1
  datasetFile.value = null
  previewingDataset.value = null
  previewSamples.value = []
  loadingDatasets.value = false
  loadingMoreDatasets.value = false
  uploadingDataset.value = false
  previewLoading.value = false
  if (datasetInput.value) datasetInput.value.value = ''
}

async function selectDatasetProject() {
  datasetRevision += 1
  const readRevision = ++datasetReadRevision
  datasetController?.abort()
  datasetController = null
  datasets.value = []
  datasetTotal.value = 0
  datasetPage.value = 1
  previewingDataset.value = null
  previewSamples.value = []
  loadingDatasets.value = false
  loadingMoreDatasets.value = false
  uploadingDataset.value = false
  previewLoading.value = false
  datasetFile.value = null
  if (datasetInput.value) datasetInput.value.value = ''
  if (!selectedProjectId.value || !sessionController) return
  datasetController = new AbortController()
  const expected = generation
  const revision = datasetRevision
  loadingDatasets.value = true
  try {
    const result = await datasetApi.list(selectedProjectId.value, 1, PAGE_SIZE, datasetController.signal)
    if (isCurrent(expected) && revision === datasetRevision && readRevision === datasetReadRevision) { datasets.value = result.items; datasetTotal.value = result.total; datasetPage.value = 1 }
  } catch (error) { if (revision === datasetRevision && readRevision === datasetReadRevision) handleError(error, expected) }
  finally { if (revision === datasetRevision) loadingDatasets.value = false }
}

async function loadMoreDatasets() {
  if (loadingMoreDatasets.value || datasets.value.length >= datasetTotal.value || !selectedProjectId.value || !datasetController) return
  const expected = generation
  const revision = datasetRevision
  const readRevision = datasetReadRevision
  const projectId = selectedProjectId.value
  const next = datasetPage.value + 1
  loadingMoreDatasets.value = true
  try {
    const result = await datasetApi.list(projectId, next, PAGE_SIZE, datasetController.signal)
    if (isCurrent(expected) && revision === datasetRevision && readRevision === datasetReadRevision && selectedProjectId.value === projectId) {
      datasets.value.push(...result.items); datasetTotal.value = result.total; datasetPage.value = next
    }
  } catch (error) { if (revision === datasetRevision && readRevision === datasetReadRevision) handleError(error, expected) }
  finally { if (revision === datasetRevision) loadingMoreDatasets.value = false }
}

function chooseDataset(event: Event) {
  datasetFile.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

async function uploadDataset() {
  if (uploadingDataset.value || !datasetFile.value || !selectedProjectId.value || !datasetController) return
  const expected = generation
  const revision = datasetRevision
  datasetReadRevision += 1 // Invalidate an older list/load-more response before starting the write.
  loadingDatasets.value = false
  loadingMoreDatasets.value = false
  uploadingDataset.value = true
  globalError.value = ''
  try {
    await datasetApi.upload(selectedProjectId.value, datasetFile.value, datasetController.signal)
    if (!isCurrent(expected) || revision !== datasetRevision) return
    datasetFile.value = null
    if (datasetInput.value) datasetInput.value.value = ''
    const readRevision = ++datasetReadRevision
    const result = await datasetApi.list(selectedProjectId.value, 1, PAGE_SIZE, datasetController.signal)
    if (isCurrent(expected) && revision === datasetRevision && readRevision === datasetReadRevision) { datasets.value = result.items; datasetTotal.value = result.total; datasetPage.value = 1 }
  } catch (error) { if (revision === datasetRevision) handleError(error, expected) }
  finally { if (revision === datasetRevision) uploadingDataset.value = false }
}

async function previewDataset(dataset: Dataset) {
  if (dataset.state !== 'ready' || !datasetController) return
  const expected = generation
  const revision = datasetRevision
  previewingDataset.value = dataset.id
  previewSamples.value = []
  previewLoading.value = true
  try {
    const result = await datasetApi.samples(dataset.id, 1, 12, datasetController.signal)
    if (isCurrent(expected) && revision === datasetRevision && previewingDataset.value === dataset.id) previewSamples.value = result.items
  } catch (error) { if (revision === datasetRevision && previewingDataset.value === dataset.id) handleError(error, expected) }
  finally { if (revision === datasetRevision && previewingDataset.value === dataset.id) previewLoading.value = false }
}

async function createUser() {
  if (creatingUser.value || !sessionController) return
  const expected = generation
  creatingUser.value = true
  globalError.value = ''
  try {
    await adminApi.createUser({ username: newUsername.value, password: newPassword.value, role: newRole.value }, sessionController.signal)
    if (!isCurrent(expected)) return
    newUsername.value = ''; newPassword.value = ''; newRole.value = 'user'
    await refreshUsers()
  } catch (error) { handleError(error, expected) }
  finally { if (expected === generation) creatingUser.value = false }
}

async function setUserActive(target: User, active: boolean) {
  if (userBusy.value || !sessionController) return
  const expected = generation
  userBusy.value = target.id
  try { await adminApi.setUserActive(target.id, active, sessionController.signal); if (isCurrent(expected)) await refreshUsers() }
  catch (error) { handleError(error, expected) }
  finally { if (expected === generation) userBusy.value = null }
}

async function changePassword() {
  if (changingPassword.value || !sessionController) return
  const expected = generation
  let activeGeneration = expected
  changingPassword.value = true
  accountMessage.value = ''
  try {
    await authApi.changePassword(currentPassword.value, replacementPassword.value, sessionController.signal)
    if (isCurrent(expected) && user.value) {
      const current = user.value
      const rotated = startSession(current)
      activeGeneration = rotated
      await loadWorkspace(rotated)
      if (isCurrent(rotated)) accountMessage.value = '密码已更新，当前会话已安全轮换。'
    }
  } catch (error) {
    if (error instanceof ApiClientError && error.status === 401) handleError(error, activeGeneration)
    else if (!isAbort(error) && isCurrent(activeGeneration)) accountMessage.value = message(error)
  } finally { if (activeGeneration === generation) changingPassword.value = false }
}

onMounted(() => { void refreshSystem(); void bootstrap() })
onUnmounted(() => { sessionController?.abort(); systemController?.abort() })
</script>

<template>
  <main v-if="booting" class="center-card" aria-live="polite"><RefreshCw class="spin" :size="24" aria-hidden="true" /><p>正在确认会话…</p></main>
  <main v-else-if="!user" class="login-page">
    <section class="login-card" aria-labelledby="login-title">
      <div class="brand"><span>EV</span><div><strong>EdgeVision</strong><small>本机目标检测工作台</small></div></div>
      <h1 id="login-title">登录工作区</h1><p>账号由管理员创建。平台不会自动生成演示账号。</p>
      <form @submit.prevent="signIn"><label>用户名<input v-model="username" required maxlength="128" autocomplete="username" /></label><label>密码<input v-model="password" required maxlength="256" type="password" autocomplete="current-password" /></label><p v-if="globalError" class="error" role="alert">{{ globalError }}</p><button class="primary" :disabled="signingIn || signingOut" type="submit">{{ signingIn ? '正在登录…' : signingOut ? '正在结束会话…' : '登录' }}</button></form>
      <div class="system-strip"><Activity :size="15" /><span>{{ checkingSystem ? '正在检查 API' : apiLive ? 'API 已连接' : 'API 未连接' }}</span><span>{{ apiReady ? '数据库就绪' : '数据库未就绪' }}</span></div>
    </section>
  </main>
  <div v-else class="workspace">
    <header><div class="brand compact"><span>EV</span><div><strong>EdgeVision</strong><small>身份与项目闭环</small></div></div><div class="account"><span>{{ user.username }} · {{ user.role === 'admin' ? '管理员' : '用户' }}</span><button :disabled="signingOut" @click="signOut"><LogOut :size="16" />{{ signingOut ? '退出中…' : '退出' }}</button></div></header>
    <div class="content">
      <p v-if="globalError" class="error banner" role="alert">{{ globalError }}</p>
      <section class="panel hero-panel"><div><small>PROJECT WORKSPACES</small><h1>项目工作区</h1><p>这里只展示真实数据库中的项目。归档保留历史，但不再接受新的业务任务。</p></div><button :disabled="refreshingProjects" @click="refreshProjects"><RefreshCw :class="{ spin: refreshingProjects }" :size="16" />刷新</button></section>
      <section class="panel status-panel"><div class="section-title"><h2><Activity :size="20" />系统与阶段</h2><button :disabled="checkingSystem" @click="refreshSystem">重新检查</button></div><div class="status-summary"><strong :class="apiLive ? 'ok' : 'bad'">{{ apiLive ? 'API 已响应' : 'API 未连接' }}</strong><strong :class="apiReady ? 'ok' : 'bad'">{{ apiReady ? '数据库已就绪' : '数据库未就绪' }}</strong></div><div class="stage-list"><span v-for="stage in stages" :key="stage[0]" :class="stage[1] ? 'available' : 'unavailable'">{{ stage[0] }} · {{ stage[1] ? '可用' : '未实现' }}</span></div></section>
      <section class="panel"><h2><FolderPlus :size="20" />新建项目</h2><form class="grid-form" @submit.prevent="createProject"><label>项目名称<input v-model="projectName" required maxlength="160" /></label><label>描述<input v-model="projectDescription" maxlength="2000" /></label><button class="primary" :disabled="creatingProject" type="submit">{{ creatingProject ? '创建中…' : '创建项目' }}</button></form></section>
      <section class="panel"><div class="section-title"><h2>项目列表</h2><span>已显示 {{ projects.length }} / {{ projectTotal }}</span></div><p v-if="projects.length === 0" class="empty">还没有项目。创建第一个检测工作区吧。</p><article v-for="project in projects" :key="project.id" class="row-card"><template v-if="editingProject === project.id"><div class="edit-grid"><input v-model="editName" required maxlength="160" aria-label="编辑项目名称" /><input v-model="editDescription" maxlength="2000" aria-label="编辑项目描述" /></div><div class="actions"><button @click="editingProject = null">取消</button><button class="primary" :disabled="projectBusy === project.id" @click="saveProject(project)">保存</button></div></template><template v-else><div><div class="row-title"><strong>{{ project.name }}</strong><span :class="project.archived_at ? 'archived' : 'active'">{{ project.archived_at ? '已归档' : '使用中' }}</span></div><p>{{ project.description || '暂无描述' }}</p><small>所有者 {{ project.owner_id }}</small></div><div class="actions"><button @click="startEdit(project)"><Pencil :size="15" />编辑</button><button :disabled="Boolean(project.archived_at) || projectBusy === project.id" @click="archiveProject(project)"><Archive :size="15" />归档</button></div></template></article><button v-if="projects.length < projectTotal" class="load-more" :disabled="loadingMoreProjects" @click="loadMoreProjects">{{ loadingMoreProjects ? '加载中…' : '加载更多项目' }}</button></section>
      <section class="panel dataset-panel"><div class="section-title"><h2><Database :size="20" />数据集快照</h2><span>上传只登记真实 pending 快照，异步校验由下一阶段接线</span></div><label class="project-picker">所属项目<select v-model="selectedProjectId" @change="selectDatasetProject"><option value="">请选择项目</option><option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }}{{ project.archived_at ? '（已归档）' : '' }}</option></select></label><form v-if="selectedProject" class="dataset-upload" @submit.prevent="uploadDataset"><label>受控 YOLO ZIP<input ref="datasetInput" type="file" accept=".zip,application/zip" :disabled="Boolean(selectedProject.archived_at) || uploadingDataset" @change="chooseDataset" /></label><button class="primary" type="submit" :disabled="!datasetFile || Boolean(selectedProject.archived_at) || uploadingDataset"><UploadCloud :size="16" />{{ uploadingDataset ? '上传中…' : '上传新快照' }}</button></form><p v-if="selectedProject?.archived_at" class="note">归档项目只读，不能继续上传。</p><p v-if="loadingDatasets" class="empty">正在读取真实数据集记录…</p><p v-else-if="selectedProject && datasets.length === 0" class="empty">这个项目还没有数据集。</p><article v-for="dataset in datasets" :key="dataset.id" class="row-card dataset-row"><div><div class="row-title"><strong>{{ dataset.name }} · v{{ dataset.version }}</strong><span :class="dataset.state">{{ dataset.state }}</span></div><p>ZIP {{ dataset.size_bytes.toLocaleString() }} bytes · SHA-256 {{ dataset.sha256.slice(0, 16) }}…</p><small>{{ dataset.state === 'pending' ? '已安全暂存，尚未校验，不能训练或预览' : dataset.state === 'ready' ? `${dataset.counts?.images ?? 0} 张图片 · ${dataset.classes.length} 类` : '校验状态来自真实记录' }}</small></div><button :disabled="dataset.state !== 'ready'" @click="previewDataset(dataset)"><Images :size="15" />有限预览</button></article><button v-if="datasets.length < datasetTotal" class="load-more" :disabled="loadingMoreDatasets" @click="loadMoreDatasets">{{ loadingMoreDatasets ? '加载中…' : '加载更多数据集' }}</button><p v-if="selectedProject && datasets.length" class="note">已显示 {{ datasets.length }} / {{ datasetTotal }}。同名 ZIP 再次上传会创建新版本，不覆盖既有快照。</p><div v-if="previewingDataset" class="preview-grid"><p v-if="previewLoading" class="empty">正在读取已验证预览…</p><article v-for="sample in previewSamples" :key="sample.id" class="preview-card"><svg :viewBox="`0 0 ${sample.width} ${sample.height}`" role="img" :aria-label="sample.image_path"><image :href="sample.image_url" x="0" y="0" :width="sample.width" :height="sample.height" preserveAspectRatio="xMidYMid meet" /><rect v-for="(annotation, index) in sample.annotations" :key="index" :x="(annotation.xywh[0] - annotation.xywh[2] / 2) * sample.width" :y="(annotation.xywh[1] - annotation.xywh[3] / 2) * sample.height" :width="annotation.xywh[2] * sample.width" :height="annotation.xywh[3] * sample.height"><title>{{ annotation.class_name }} · class {{ annotation.class_id }}</title></rect></svg><strong>{{ sample.split }} · {{ sample.image_path }}</strong><small>{{ sample.width }}×{{ sample.height }} · {{ sample.annotations.map(item => item.class_name).join('、') || '显式背景' }}{{ sample.annotations_truncated ? '（框已截断）' : '' }}</small></article><p v-if="!previewLoading && previewSamples.length === 0" class="empty">该 ready 数据集没有可用的有限预览摘要。</p></div></section>
      <section class="panel"><h2><ShieldCheck :size="20" />账号安全</h2><form class="grid-form" @submit.prevent="changePassword"><label>当前密码<input v-model="currentPassword" required type="password" autocomplete="current-password" /></label><label>新密码<input v-model="replacementPassword" required minlength="12" maxlength="256" type="password" autocomplete="new-password" /></label><button :disabled="changingPassword" type="submit">{{ changingPassword ? '更新中…' : '修改密码' }}</button></form><p v-if="accountMessage" class="note" aria-live="polite">{{ accountMessage }}</p></section>
      <section v-if="isAdmin" class="panel"><div class="section-title"><h2><UserPlus :size="20" />用户管理</h2><span>已显示 {{ users.length }} / {{ userTotal }}</span></div><form class="grid-form admin-create" @submit.prevent="createUser"><label>用户名<input v-model="newUsername" required maxlength="128" /></label><label>初始密码<input v-model="newPassword" required minlength="12" maxlength="256" type="password" autocomplete="new-password" /></label><label>角色<select v-model="newRole"><option value="user">普通用户</option><option value="admin">管理员</option></select></label><button class="primary" :disabled="creatingUser" type="submit">{{ creatingUser ? '创建中…' : '创建用户' }}</button></form><article v-for="entry in users" :key="entry.id" class="row-card user-row"><div><div class="row-title"><strong>{{ entry.username }}</strong><span>{{ entry.role }}</span></div><small>{{ entry.is_active ? '账号已启用' : '账号已禁用' }}</small></div><button :disabled="userBusy === entry.id" @click="setUserActive(entry, !entry.is_active)">{{ entry.is_active ? '禁用' : '启用' }}</button></article><button v-if="users.length < userTotal" class="load-more" :disabled="loadingMoreUsers" @click="loadMoreUsers">{{ loadingMoreUsers ? '加载中…' : '加载更多用户' }}</button></section>
    </div>
  </div>
</template>
