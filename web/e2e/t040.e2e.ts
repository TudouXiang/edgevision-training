import { expect, test } from '@playwright/test'

function required(name: string) {
  const value = process.env[name]
  if (!value) throw new Error(`Isolated harness must provide ${name}`)
  return value
}

test('real Worker validates uploaded datasets, persists final logs, previews and downloadable invalid reports', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('用户名', { exact: true }).fill(required('EDGEVISION_E2E_ADMIN_USERNAME'))
  await page.getByLabel('密码', { exact: true }).fill(required('EDGEVISION_E2E_ADMIN_PASSWORD'))
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '项目工作区' })).toBeVisible()
  const projectName = `worker-project-${Date.now()}`
  await page.getByLabel('项目名称').fill(projectName)
  const projectResponse = page.waitForResponse(response => response.url().endsWith('/api/v1/projects') && response.request().method() === 'POST')
  await page.getByRole('button', { name: '创建项目' }).click()
  const project = await (await projectResponse).json() as { id: string }
  await page.getByLabel('所属项目').selectOption(project.id)
  await page.getByLabel('受控 YOLO ZIP').setInputFiles(required('EDGEVISION_E2E_DATASET_ZIP'))
  await page.getByRole('button', { name: '上传新快照' }).click()
  const validRow = page.locator('article.dataset-row').filter({ hasText: 'tiny-dataset · v1' })
  await expect(validRow).toContainText('pending')
  let checkPosts = 0
  page.on('request', request => { if (request.url().endsWith('/check') && request.method() === 'POST') checkPosts += 1 })
  const submitted = page.waitForResponse(response => response.url().endsWith('/check') && response.request().method() === 'POST')
  await validRow.getByRole('button', { name: '开始校验' }).evaluate((button: HTMLButtonElement) => { button.click(); button.click() })
  const accepted = await submitted
  expect(accepted.status()).toBe(202)
  const job = await accepted.json() as { job_id: string; state: string }
  expect(job.state).toBe('queued')
  expect(checkPosts).toBe(1)
  await expect(validRow).toContainText('ready', { timeout: 20_000 })
  await expect(validRow).toContainText('2 张图片 · 1 类')
  await expect(page.getByRole('region', { name: '任务日志' })).toContainText('Dataset validation passed')
  await expect(page.getByRole('region', { name: '任务日志' })).toContainText('已读取最终日志')
  await validRow.getByRole('button', { name: '有限预览' }).click()
  await expect(page.locator('.preview-card')).toHaveCount(2)
  const reportHref = await validRow.getByRole('link', { name: '下载报告' }).getAttribute('href')
  const report = await page.request.get(reportHref!)
  expect(report.status()).toBe(200)
  expect((await report.json()).job_id).toBe(job.job_id)
  await page.getByRole('button', { name: '关闭日志' }).click()
  await expect(page.getByRole('region', { name: '任务日志' })).toHaveCount(0)
  await page.reload()
  await page.getByLabel('所属项目').selectOption(project.id)
  await expect(validRow).toContainText('ready')
  await expect(page.locator('.job-row').first()).toContainText('succeeded')

  await page.getByLabel('受控 YOLO ZIP').setInputFiles(required('EDGEVISION_E2E_INVALID_DATASET_ZIP'))
  await page.getByRole('button', { name: '上传新快照' }).click()
  const invalidRow = page.locator('article.dataset-row').filter({ hasText: 'invalid-dataset · v1' })
  await expect(invalidRow).toContainText('pending')
  await invalidRow.getByRole('button', { name: '开始校验' }).click()
  await expect(invalidRow.locator('.row-title span')).toHaveText('invalid', { timeout: 20_000 })
  await expect(invalidRow.getByRole('link', { name: '下载报告' })).toBeVisible()
  await expect(invalidRow.getByRole('button', { name: '有限预览' })).toBeDisabled()
  const invalidReport = await page.request.get((await invalidRow.getByRole('link', { name: '下载报告' }).getAttribute('href'))!)
  expect(invalidReport.status()).toBe(200)
  const rejected = await invalidReport.json()
  expect(rejected.valid).toBe(false)
  expect(rejected.errors[0].code).toBe('LABEL_CLASS_RANGE')
  await expect(page.locator('.job-row').first()).toContainText('failed')
  await page.setViewportSize({ width: 375, height: 812 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
