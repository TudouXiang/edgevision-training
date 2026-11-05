import { createHash } from 'node:crypto'
import { expect, type Page } from '@playwright/test'
import type { components } from '../../contracts/generated/openapi'

type Job = components['schemas']['JobPublic']
type Artifact = components['schemas']['ArtifactPublic']

// Called only by the explicitly delivery-enabled one-epoch training scenario.
// Download bytes remain in the disposable browser context, never in reports.
export async function verifyExport(page: Page, projectId: string, trainingJobId: string) {
  const capabilities = await (await page.request.get('/api/v1/capabilities')).json()
  expect(capabilities.features.onnx_export.available).toBe(true)
  expect(capabilities.features.onnx_inference.available).toBe(false)
  expect(capabilities.features.deployment.available).toBe(false)
  const inventory = await (await page.request.get(`/api/v1/projects/${projectId}/artifacts?page_size=100`)).json()
  const sources: Artifact[] = inventory.items.filter((item: Artifact) => item.job_id === trainingJobId && item.validation_state === 'passed' && ['pt_best', 'pt_last'].includes(item.kind))
  expect(sources).toHaveLength(2)
  const source = sources.find(item => item.kind === 'pt_best')!
  const panel = page.locator('.export-panel')
  await panel.getByRole('button', { name: '刷新导出状态' }).click()
  await expect(panel.getByLabel('来源模型').locator('option', { hasText: source.id })).toHaveCount(1)
  await panel.getByLabel('来源模型').selectOption(source.id)
  const submitted = page.waitForResponse(response => response.url().endsWith(`/projects/${projectId}/jobs`) && response.request().method() === 'POST' && response.request().postDataJSON()?.kind === 'export_onnx')
  await panel.getByRole('button', { name: '创建 ONNX 导出任务' }).evaluate((button: HTMLButtonElement) => { button.click(); button.click() })
  const accepted = await submitted
  expect(accepted.status()).toBe(202)
  const job = await accepted.json()
  await expect(panel.locator('h3')).toContainText('succeeded', { timeout: 120000 })
  await expect(panel).toContainText('已读取最终日志')
  const jobPage = await (await page.request.get(`/api/v1/projects/${projectId}/jobs?page_size=100`)).json()
  expect(jobPage.items.filter((item: Job) => item.kind === 'export_onnx')).toHaveLength(1)
  expect(jobPage.items.filter((item: Job) => item.kind === 'train')).toHaveLength(1)
  const artifacts = await (await page.request.get(`/api/v1/projects/${projectId}/artifacts?page_size=100`)).json()
  const outputs: Artifact[] = artifacts.items.filter((item: Artifact) => item.job_id === job.job_id && item.kind === 'onnx' && item.validation_state === 'passed')
  expect(outputs).toHaveLength(1)
  const output = outputs[0]
  if (output.kind !== 'onnx') throw new Error('Expected a strictly validated ONNX artifact')
  expect(output.metadata.provenance.parent_artifact_id).toBe(source.id)
  expect(output.metadata.provenance.source_job_id).toBe(trainingJobId)
  expect(output.metadata.provenance.source_sha256).toBe(source.sha256)
  const proof = output.metadata.validation
  expect(proof.job_id).toBe(job.job_id); expect(proof.model_sha256).toBe(output.sha256)
  expect(proof.original_graph_sha256).toBe(output.sha256); expect(proof.model_size_bytes).toBe(output.size_bytes)
  expect(proof.checker_passed).toBe(true); expect(proof.runtime.provider).toBe('CPUExecutionProvider')
  expect(proof.samples.map(item => item.name)).toEqual(['zeros', 'gradient', 'pattern'])
  expect(proof.samples.every(item => item.passed && Number.isFinite(item.max_tolerance_ratio) && item.max_tolerance_ratio <= 1)).toBe(true)
  await expect(panel.getByRole('link', { name: /下载已验证 ONNX/ })).toHaveCount(1)
  const downloadEvent = page.waitForEvent('download')
  await panel.getByRole('link', { name: /下载已验证 ONNX/ }).click()
  const download = await downloadEvent
  expect(await download.failure()).toBeNull()
  expect(download.suggestedFilename()).toMatch(/\.onnx$/)
  const stream = await download.createReadStream()
  expect(stream).not.toBeNull()
  const digest = createHash('sha256'); let size = 0
  for await (const chunk of stream!) { size += chunk.length; digest.update(chunk) }
  expect(size).toBe(output.size_bytes); expect(digest.digest('hex')).toBe(output.sha256)
  await download.delete()
  await page.context().setOffline(true)
  await expect(panel.getByRole('alert')).toContainText('将自动重试', { timeout: 20000 })
  await page.context().setOffline(false)
  await expect(panel.getByRole('alert')).toHaveCount(0, { timeout: 20000 })
  await page.goto('/onnx'); await page.getByLabel('所属项目').selectOption(projectId)
  await expect(page.locator('.export-panel h3')).toContainText('succeeded')
  await expect(page.locator('.export-panel').getByRole('link', { name: /下载已验证 ONNX/ })).toHaveCount(1)
  await page.locator('.export-panel').getByLabel('来源模型').selectOption(source.id)
  const replayed = page.waitForResponse(response => response.url().endsWith(`/projects/${projectId}/jobs`) && response.request().method() === 'POST' && response.request().postDataJSON()?.kind === 'export_onnx')
  await page.locator('.export-panel').getByRole('button', { name: '创建 ONNX 导出任务' }).click()
  const replay = await replayed
  expect(replay.status()).toBe(202); expect((await replay.json()).job_id).toBe(job.job_id)
  await expect(page.locator('.export-panel h3')).toContainText('succeeded')
  const afterReload = await (await page.request.get(`/api/v1/projects/${projectId}/jobs?page_size=100`)).json()
  expect(afterReload.items.filter((item: Job) => item.kind === 'export_onnx')).toHaveLength(1)
}
