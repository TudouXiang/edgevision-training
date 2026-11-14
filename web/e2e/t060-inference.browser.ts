import { createHash } from 'node:crypto'
import { readFile, writeFile } from 'node:fs/promises'
import { expect, test, type Page } from '@playwright/test'
import type { components } from '../../contracts/generated/openapi'

type Artifact = components['schemas']['ArtifactPublic']
type Job = components['schemas']['JobPublic']
type Result = components['schemas']['InferenceResult']
function required(name: string) { const value = process.env[name]; if (!value) throw new Error(`Harness must provide ${name}`); return value }
const digest = (value: Uint8Array) => createHash('sha256').update(value).digest('hex')
async function artifacts(page: Page, projectId: string) {
  const items: Artifact[] = []
  for (let pageNumber = 1; pageNumber <= 100; pageNumber++) {
    const response = await page.request.get(`/api/v1/projects/${encodeURIComponent(projectId)}/artifacts?page=${pageNumber}&page_size=100`)
    expect(response.status()).toBe(200)
    const body: components['schemas']['Page_ArtifactPublic_'] = await response.json()
    items.push(...body.items); if (items.length >= body.total) return items
    if (!body.items.length) break
  }
  throw new Error('Incomplete artifact inventory')
}
async function jobs(page: Page, projectId: string) {
  const items: Job[] = []
  for (let pageNumber = 1; pageNumber <= 100; pageNumber++) {
    const response = await page.request.get(`/api/v1/projects/${encodeURIComponent(projectId)}/jobs?page=${pageNumber}&page_size=100`)
    expect(response.status()).toBe(200)
    const body: components['schemas']['Page_JobPublic_'] = await response.json()
    items.push(...body.items); if (items.length >= body.total) return items
    if (!body.items.length) break
  }
  throw new Error('Incomplete job inventory')
}

// Dedicated opt-in suite. Its owner must have finished the real HTTP stages,
// drained the old Worker, run the production I probe under the same lock/root,
// and restarted the services. No training, probe, fake runner, or seed DB writes
// happen in this browser test. Credentials, images, and downloaded bytes stay in
// the disposable context/runtime; the anonymous reporter publishes no artifacts.
test('real PT and ONNX single-image UI preserves job identity and verified results', async ({ page, context }) => {
  // Stay inside the harness's 150-second browser-child ceiling. Timeouts fail;
  // they never skip a backend or downgrade the checks below.
  test.setTimeout(135_000)
  // Fixed phase literals only. Never serialize assertions, inputs or errors.
  const checkpoint = async (phase: string) => {
    const destination = process.env.EDGEVISION_E2E_INFERENCE_PHASE_FILE
    if (destination) await writeFile(destination, JSON.stringify({ phase }), { mode: 0o600 })
  }
  await checkpoint('ui_setup')
  expect(process.env.EDGEVISION_E2E_INFERENCE).toBe('1')
  const base = new URL(required('EDGEVISION_E2E_BASE_URL'))
  if (!['http:', 'https:'].includes(base.protocol) || !['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname)) throw new Error('Inference harness must use loopback services')
  const session: unknown = JSON.parse(required('EDGEVISION_E2E_INFERENCE_SESSION'))
  if (!session || typeof session !== 'object' || Object.keys(session).sort().join(',') !== 'edgevision_csrf,edgevision_session') throw new Error('Invalid private session handoff')
  for (const name of ['edgevision_session', 'edgevision_csrf'] as const) {
    const value = (session as Record<string, unknown>)[name]
    if (typeof value !== 'string' || !value || /[\x00-\x20\x7f]/.test(value)) throw new Error('Invalid private session handoff')
    await context.addCookies([{ name, value, url: base.origin, httpOnly: name === 'edgevision_session', secure: base.protocol === 'https:', sameSite: 'Lax' }])
  }
  const projectId = required('EDGEVISION_E2E_INFERENCE_PROJECT_ID'), ptId = required('EDGEVISION_E2E_INFERENCE_PT_ID'), onnxId = required('EDGEVISION_E2E_INFERENCE_ONNX_ID')
  const imagePath = required('EDGEVISION_E2E_INFERENCE_IMAGE'), bytes = await readFile(imagePath)
  // The harness supplies its private, metadata-free synthetic PNG, not a user image.
  expect(bytes.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a'); expect(bytes.subarray(12, 16).toString()).toBe('IHDR')
  const width = bytes.readUInt32BE(16), height = bytes.readUInt32BE(20), imageSha = digest(bytes)
  expect(width).toBeGreaterThan(0); expect(height).toBeGreaterThan(0)
  await checkpoint('ui_capabilities')
  const capabilityResponse = await page.request.get('/api/v1/capabilities'); expect(capabilityResponse.status()).toBe(200)
  const capability: components['schemas']['CapabilitiesResponse'] = await capabilityResponse.json()
  expect(capability.features.pt_inference.available).toBe(true); expect(capability.features.onnx_inference.available).toBe(true); expect(capability.features.deployment.available).toBe(false)
  await checkpoint('ui_inventory')
  const inventory = await artifacts(page, projectId)
  const pt = inventory.find(item => item.id === ptId), onnx = inventory.find(item => item.id === onnxId)
  if (!pt || !['pt_best', 'pt_last'].includes(pt.kind) || pt.format !== 'pt' || !onnx || onnx.kind !== 'onnx') throw new Error('Harness source models do not match the required kinds')
  for (const source of [pt, onnx]) {
    expect(source.project_id).toBe(projectId); expect(source.validation_state).toBe('passed'); expect(source.job_id).toBeTruthy()
    const response = await page.request.get(`/api/v1/jobs/${encodeURIComponent(source.job_id!)}`); expect(response.status()).toBe(200)
    const job: Job = await response.json(); expect(job.project_id).toBe(projectId); expect(job.state).toBe('succeeded'); expect(job.kind).toBe(source.kind === 'onnx' ? 'export_onnx' : 'train')
  }
  expect(onnx.metadata.provenance.parent_artifact_id).toBe(ptId)
  await checkpoint('ui_upload')
  await page.goto('/inference'); await page.getByLabel('所属项目').selectOption(projectId)
  const panel = page.locator('.inference-panel')
  await panel.getByLabel('上传单张图片').setInputFiles(imagePath)
  const uploadedResponse = page.waitForResponse(response => response.url().endsWith(`/projects/${projectId}/images`) && response.request().method() === 'POST')
  await panel.getByRole('button', { name: '上传未验证输入', exact: true }).click()
  const uploadResponse = await uploadedResponse; expect(uploadResponse.status()).toBe(201)
  const input: components['schemas']['InferenceInputArtifactPublic'] = await uploadResponse.json()
  expect(input.project_id).toBe(projectId); expect(input.kind).toBe('inference_input'); expect(input.job_id).toBeNull(); expect(input.validation_state).toBe('unverified')
  expect(input.sha256).toBe(imageSha); expect(input.size_bytes).toBe(bytes.length); expect(input.metadata.validation_scope).toBe('bounded_upload_bytes')
  await expect(panel.getByLabel('不可变图片输入')).toHaveValue(input.id)
  await expect(panel.locator('.inference-preview')).toHaveCount(0); await expect(panel.getByRole('link')).toHaveCount(0)

  let lastJobId = ''
  for (const backend of ['pt', 'onnx'] as const) {
    await checkpoint(`ui_${backend}_submit_inventory`)
    const source = backend === 'pt' ? pt : onnx, before = new Set((await jobs(page, projectId)).map(job => job.id))
    await checkpoint(`ui_${backend}_submit_model`)
    await panel.getByLabel('执行后端').selectOption(backend)
    await expect(panel.getByLabel('来源模型').locator('option', { hasText: source.id })).toHaveCount(1)
    await panel.getByLabel('来源模型').selectOption(source.id); await panel.getByLabel('不可变图片输入').selectOption(input.id)
    await checkpoint(`ui_${backend}_submit_thresholds`)
    await panel.getByLabel('置信度阈值').fill('0.25'); await panel.getByLabel('IoU 阈值').fill('0.45')
    await checkpoint(`ui_${backend}_submit_ready`)
    const submit = panel.getByRole('button', { name: '创建推理任务', exact: true })
    await expect(submit).toBeEnabled()
    await checkpoint(`ui_${backend}_submit_request`)
    const acceptedResponse = page.waitForResponse(response => response.url().endsWith(`/projects/${projectId}/jobs`) && response.request().method() === 'POST' && response.request().postDataJSON()?.kind === 'infer')
    await submit.evaluate((button: HTMLButtonElement) => { button.click(); button.click() })
    const response = await acceptedResponse
    await checkpoint(`ui_${backend}_submit_response`)
    expect(response.status()).toBe(202)
    const accepted: components['schemas']['JobAccepted'] = await response.json(); lastJobId = accepted.job_id
    await checkpoint(`ui_${backend}_result`)
    await expect(panel.locator('h3')).toContainText('succeeded', { timeout: 45_000 })
    await expect(panel.getByRole('region', { name: '推理日志' })).toContainText('已读取最终日志')
    const newJobs = (await jobs(page, projectId)).filter(job => !before.has(job.id))
    expect(newJobs).toHaveLength(1); expect(newJobs[0].id).toBe(accepted.job_id); expect(newJobs[0].kind).toBe('infer')
    expect(newJobs[0].inference?.params).toEqual({ backend, model_artifact_id: source.id, image_artifact_id: input.id, confidence: .25, iou: .45 })
    const outputs = (await artifacts(page, projectId)).filter(item => item.job_id === accepted.job_id && item.kind === 'inference_result' && item.validation_state === 'passed')
    expect(outputs).toHaveLength(1); const output = outputs[0]
    const resultResponse = await page.request.get(`/api/v1/inferences/${encodeURIComponent(output.id)}`); expect(resultResponse.status()).toBe(200)
    const result: Result = await resultResponse.json(), provider = backend === 'pt' ? 'pytorch_cpu' : 'CPUExecutionProvider'
    expect(result.artifact_id).toBe(output.id); expect(result.backend).toBe(backend); expect(result.provider).toBe(provider)
    expect(result.runtime.backend).toBe(backend); expect(result.runtime.provider).toBe(provider); expect(result.protocol).toBe('detection-image-v1')
    expect(result.provenance.project_id).toBe(projectId); expect(result.provenance.job_id).toBe(accepted.job_id)
    expect(result.provenance.model_artifact_id).toBe(source.id); expect(result.provenance.model_sha256).toBe(source.sha256)
    expect(result.provenance.image_artifact_id).toBe(input.id); expect(result.provenance.image_sha256).toBe(imageSha)
    expect(result.params).toEqual(newJobs[0].inference?.params); expect(result.image_width).toBe(width); expect(result.image_height).toBe(height)
    expect(result.preview.width).toBeLessThanOrEqual(1280); expect(result.preview.height).toBeLessThanOrEqual(1280)
    expect(result.detections.length).toBeLessThanOrEqual(300)
    for (const detection of result.detections) {
      expect(Number.isInteger(detection.class_id) && detection.class_id >= 0 && detection.class_id < result.classes.length).toBe(true)
      expect(Number.isFinite(detection.score) && detection.score >= 0 && detection.score <= 1).toBe(true)
      const [x1, y1, x2, y2] = detection.xyxy
      expect(detection.xyxy.every(Number.isFinite) && 0 <= x1 && x1 < x2 && x2 <= width && 0 <= y1 && y1 < y2 && y2 <= height).toBe(true)
    }
    await checkpoint(`ui_${backend}_preview`)
    await expect(panel.locator('.verified-inference')).toContainText(provider)
    await expect(panel.locator('.inference-preview')).toHaveAttribute('viewBox', `0 0 ${width} ${height}`)
    await expect(panel.locator('.inference-preview image')).toHaveAttribute('width', String(width)); await expect(panel.locator('.inference-preview image')).toHaveAttribute('height', String(height))
    const decoded = await panel.locator('.inference-preview image').evaluate(async element => {
      const source = element.getAttribute('href'); if (!source?.startsWith('blob:')) throw new Error('Expected an authenticated fetched preview')
      const raster = new Image(); raster.src = source; await raster.decode(); return [raster.naturalWidth, raster.naturalHeight]
    })
    expect(decoded).toEqual([result.preview.width, result.preview.height])
    const boxes = await panel.locator('.inference-preview rect').evaluateAll(elements => elements.map(element => ['x', 'y', 'width', 'height'].map(name => Number(element.getAttribute(name)))))
    expect(boxes).toEqual(result.detections.map(({ xyxy: [x1, y1, x2, y2] }) => [x1, y1, x2 - x1, y2 - y1]))
    if (!result.detections.length) await expect(panel).toContainText('合法的空检测成功结果')
    const previewResponse = await page.request.get(`/api/v1/inferences/${encodeURIComponent(output.id)}/image`); expect(previewResponse.status()).toBe(200)
    expect(previewResponse.headers()['content-type']).toContain('image/png'); const previewBytes = await previewResponse.body()
    expect(previewBytes.length).toBe(result.preview.size_bytes); expect(digest(previewBytes)).toBe(result.preview.sha256)
    await checkpoint(`ui_${backend}_download`)
    const downloadEvent = page.waitForEvent('download'); await panel.getByRole('link', { name: '下载结果 JSON', exact: true }).click()
    const download = await downloadEvent; expect(await download.failure()).toBeNull(); expect(download.suggestedFilename()).toMatch(/\.json$/)
    const stream = await download.createReadStream(); expect(stream).not.toBeNull(); const hash = createHash('sha256'); let size = 0
    for await (const chunk of stream!) { size += chunk.length; hash.update(chunk) }
    expect(size).toBe(output.size_bytes); expect(hash.digest('hex')).toBe(output.sha256); await download.delete()
    await checkpoint(`ui_${backend}_reload`)
    await page.reload(); await page.getByLabel('所属项目').selectOption(projectId)
    await expect(panel.locator('.inference-detail > .identity')).toHaveText(accepted.job_id)
    await expect(panel.locator('.verified-inference')).toContainText(provider)
    await expect(panel.getByRole('button', { name: '已接收推理任务', exact: true })).toBeDisabled()
    expect((await jobs(page, projectId)).filter(job => !before.has(job.id))).toHaveLength(1)
  }
  await checkpoint('ui_offline')
  await context.setOffline(true)
  await expect(panel.getByRole('alert')).toContainText('将自动重试', { timeout: 20_000 })
  await checkpoint('ui_recovery')
  await context.setOffline(false)
  await expect(panel.getByRole('alert')).toHaveCount(0, { timeout: 20_000 })
  await page.goto('/inference'); await page.getByLabel('所属项目').selectOption(projectId)
  await expect(panel.locator('.inference-detail > .identity')).toHaveText(lastJobId)
  await expect(panel.locator('.verified-inference')).toContainText('CPUExecutionProvider')
  await checkpoint('ui_responsive')
  await page.setViewportSize({ width: 375, height: 812 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  const finalCapabilities: components['schemas']['CapabilitiesResponse'] = await (await page.request.get('/api/v1/capabilities')).json()
  expect(finalCapabilities.features.deployment.available).toBe(false)
  await checkpoint('ui_complete')
})
