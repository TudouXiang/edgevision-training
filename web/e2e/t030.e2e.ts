import { expect, type Page, test } from '@playwright/test'

function required(name: string): string {
  const value = process.env[name]
  if (!value) throw new Error(`The isolated browser harness must provide ${name}`)
  return value
}

async function login(page: Page) {
  await page.goto('/')
  await page.getByLabel('用户名', { exact: true }).fill(required('EDGEVISION_E2E_ADMIN_USERNAME'))
  await page.getByLabel('密码', { exact: true }).fill(required('EDGEVISION_E2E_ADMIN_PASSWORD'))
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '项目工作区' })).toBeVisible()
}

async function sameOrigin(page: Page, path: string, method = 'GET', extraHeaders: Record<string, string> = {}) {
  return page.evaluate(async ({ path, method, extraHeaders }) => {
    const prefix = 'edgevision_csrf='
    const csrf = document.cookie.split(';').map(value => value.trim()).find(value => value.startsWith(prefix))?.slice(prefix.length)
    const response = await fetch(`/api/v1${path}`, {
      method,
      credentials: 'same-origin',
      headers: { ...extraHeaders, ...(method === 'GET' || !csrf ? {} : { 'X-CSRF-Token': decodeURIComponent(csrf) }) },
    })
    return { status: response.status, body: await response.json().catch(() => null) }
  }, { path, method, extraHeaders })
}

test('real bounded dataset upload creates immutable pending versions and archived projects disable upload', async ({ page }) => {
  await login(page)
  await expect(page.getByText('数据集 · 可用', { exact: true })).toBeVisible()

  const projectName = `dataset-project-${Date.now()}`
  const projectResponse = page.waitForResponse(response => response.url().endsWith('/api/v1/projects') && response.request().method() === 'POST')
  await page.getByLabel('项目名称').fill(projectName)
  await page.getByLabel('描述', { exact: true }).fill('T030 browser dataset project')
  await page.getByRole('button', { name: '创建项目' }).click()
  const createdProjectResponse = await projectResponse
  expect(createdProjectResponse.status()).toBe(201)
  const project = await createdProjectResponse.json() as { id: string }

  const initialList = page.waitForResponse(response => response.url().includes(`/api/v1/projects/${project.id}/datasets?`) && response.request().method() === 'GET')
  await page.getByLabel('所属项目').selectOption(project.id)
  expect((await initialList).status()).toBe(200)
  await expect(page.getByText('这个项目还没有数据集。')).toBeVisible()

  const fixture = required('EDGEVISION_E2E_DATASET_ZIP')
  await page.getByLabel('受控 YOLO ZIP').setInputFiles(fixture)
  let uploadPosts = 0
  page.on('request', request => {
    if (request.url().endsWith(`/api/v1/projects/${project.id}/datasets`) && request.method() === 'POST') uploadPosts += 1
  })
  const firstUpload = page.waitForResponse(response => response.url().endsWith(`/api/v1/projects/${project.id}/datasets`) && response.request().method() === 'POST')
  await page.getByRole('button', { name: '上传新快照' }).evaluate((button: HTMLButtonElement) => { button.click(); button.click() })
  const firstResponse = await firstUpload
  expect(firstResponse.status()).toBe(201)
  const first = await firstResponse.json() as { id: string; state: string; version: number; sha256: string }
  expect(first.state).toBe('pending')
  expect(first.version).toBe(1)
  expect(first.sha256).toMatch(/^[0-9a-f]{64}$/)
  await expect(page.locator('article.dataset-row').filter({ hasText: 'tiny-dataset · v1' })).toContainText('已安全暂存，尚未校验，不能训练或预览')
  expect(uploadPosts).toBe(1)
  const detail = await sameOrigin(page, `/datasets/${first.id}`)
  expect(detail.status).toBe(200)
  expect((detail.body as { state: string }).state).toBe('pending')
  const pendingPreview = await sameOrigin(page, `/datasets/${first.id}/samples`)
  expect(pendingPreview.status).toBe(409)
  expect((pendingPreview.body as { error: { code: string } }).error.code).toBe('DATASET_NOT_READY')
  const unavailableCheck = await sameOrigin(page, `/datasets/${first.id}/check`, 'POST', { 'Idempotency-Key': 't030-browser-check' })
  expect(unavailableCheck.status).toBe(501)
  expect((unavailableCheck.body as { error: { code: string } }).error.code).toBe('NOT_IMPLEMENTED')

  await page.getByLabel('受控 YOLO ZIP').setInputFiles(fixture)
  const secondUpload = page.waitForResponse(response => response.url().endsWith(`/api/v1/projects/${project.id}/datasets`) && response.request().method() === 'POST')
  await page.getByRole('button', { name: '上传新快照' }).click()
  const secondResponse = await secondUpload
  expect(secondResponse.status()).toBe(201)
  const second = await secondResponse.json() as { id: string; version: number; state: string }
  expect(second.id).not.toBe(first.id)
  expect(second.version).toBe(2)
  expect(second.state).toBe('pending')
  await expect(page.locator('article.dataset-row').filter({ hasText: 'tiny-dataset · v1' })).toBeVisible()
  await expect(page.locator('article.dataset-row').filter({ hasText: 'tiny-dataset · v2' })).toBeVisible()

  await page.reload()
  const persistedList = page.waitForResponse(response => response.url().includes(`/api/v1/projects/${project.id}/datasets?`))
  await page.getByLabel('所属项目').selectOption(project.id)
  expect((await persistedList).status()).toBe(200)
  await expect(page.locator('article.dataset-row')).toHaveCount(2)

  const projectRow = page.locator('article.row-card').filter({ hasText: projectName }).filter({ has: page.getByRole('button', { name: '归档' }) })
  const archive = page.waitForResponse(response => response.url().endsWith(`/api/v1/projects/${project.id}/archive`))
  await projectRow.getByRole('button', { name: '归档' }).click()
  expect((await archive).status()).toBe(200)
  await expect(page.getByText('归档项目只读，不能继续上传。')).toBeVisible()
  await expect(page.getByRole('button', { name: '上传新快照' })).toBeDisabled()
})
