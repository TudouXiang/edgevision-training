import { expect, type Browser, type BrowserContext, type Page, test } from '@playwright/test'

type Credentials = { username: string; password: string }

function required(name: string): string {
  const value = process.env[name]
  if (!value) throw new Error(`The isolated browser harness must provide ${name}`)
  return value
}

function fixtures() {
  return {
    admin: { username: required('EDGEVISION_E2E_ADMIN_USERNAME'), password: required('EDGEVISION_E2E_ADMIN_PASSWORD') },
    user: { username: required('EDGEVISION_E2E_USER_USERNAME'), password: required('EDGEVISION_E2E_USER_PASSWORD') },
    rotatedPassword: required('EDGEVISION_E2E_ROTATED_PASSWORD'),
  }
}

async function login(page: Page, credentials: Credentials) {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '登录工作区' })).toBeVisible()
  await page.getByLabel('用户名', { exact: true }).fill(credentials.username)
  await page.getByLabel('密码', { exact: true }).fill(credentials.password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '项目工作区' })).toBeVisible()
}

async function contextPage(browser: Browser, baseURL: string): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL, locale: 'zh-CN', reducedMotion: 'reduce' })
  return { context, page: await context.newPage() }
}

async function sameOrigin(page: Page, path: string, init?: { method?: string; body?: unknown; headers?: Record<string, string> }) {
  return page.evaluate(async ({ path, init }) => {
    const csrfPrefix = 'edgevision_csrf='
    const csrf = document.cookie.split(';').map(value => value.trim()).find(value => value.startsWith(csrfPrefix))?.slice(csrfPrefix.length)
    const headers: Record<string, string> = { ...init?.headers }
    if (init?.body !== undefined) headers['Content-Type'] = 'application/json'
    if (init?.method && !['GET', 'HEAD', 'OPTIONS'].includes(init.method) && csrf) headers['X-CSRF-Token'] = decodeURIComponent(csrf)
    const response = await fetch(`/api/v1${path}`, {
      method: init?.method ?? 'GET', headers,
      body: init?.body === undefined ? undefined : JSON.stringify(init.body), credentials: 'same-origin',
    })
    return { status: response.status, body: await response.json().catch(() => null) }
  }, { path, init })
}

test('real identity, administration, ownership and project lifecycle', async ({ page, browser, baseURL }) => {
  const { admin, user, rotatedPassword } = fixtures()
  const root = baseURL as string

  await page.goto('/')
  await page.getByLabel('用户名', { exact: true }).fill(admin.username)
  await page.getByLabel('密码', { exact: true }).fill(`${admin.password}-wrong`)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText('Username or password is incorrect')
  await page.getByLabel('用户名', { exact: true }).fill(admin.username)
  await page.getByLabel('密码', { exact: true }).fill(admin.password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '项目工作区' })).toBeVisible()
  await page.reload()
  await expect(page.getByText('数据库已就绪', { exact: true })).toBeVisible()

  const createUser = page.waitForResponse(response => response.url().endsWith('/api/v1/admin/users') && response.request().method() === 'POST')
  await page.getByLabel('用户名', { exact: true }).fill(user.username)
  await page.getByLabel('初始密码', { exact: true }).fill(user.password)
  await page.getByRole('button', { name: '创建用户' }).click()
  expect((await createUser).status()).toBe(201)
  const userRow = page.locator('article.user-row').filter({ hasText: user.username })
  await expect(userRow).toContainText('账号已启用')

  await page.getByLabel('用户名', { exact: true }).fill(user.username)
  await page.getByLabel('初始密码', { exact: true }).fill(user.password)
  await page.getByRole('button', { name: '创建用户' }).click()
  await expect(page.getByRole('alert')).toHaveText('Username already exists')

  const projectName = `admin-project-${Date.now()}`
  const projectDescription = 'real browser project'
  let projectPosts = 0
  page.on('request', request => {
    if (request.url().endsWith('/api/v1/projects') && request.method() === 'POST') projectPosts += 1
  })
  const createProject = page.waitForResponse(response => response.url().endsWith('/api/v1/projects') && response.request().method() === 'POST')
  await page.getByLabel('项目名称').fill(projectName)
  await page.getByLabel('描述', { exact: true }).fill(projectDescription)
  await page.getByRole('button', { name: '创建项目' }).evaluate((button: HTMLButtonElement) => { button.click(); button.click() })
  const createdResponse = await createProject
  expect(createdResponse.status()).toBe(201)
  await page.waitForTimeout(200)
  expect(projectPosts).toBe(1)
  const createdProject = await createdResponse.json() as { id: string }
  let projectRow = page.locator('article.row-card').filter({ hasText: projectName })
  await expect(projectRow).toContainText(projectDescription)

  await projectRow.getByRole('button', { name: '编辑' }).click()
  await page.getByLabel('编辑项目名称').fill(`${projectName}-cancelled`)
  await page.getByRole('button', { name: '取消' }).click()
  await expect(projectRow.getByText(projectName, { exact: true })).toBeVisible()
  await projectRow.getByRole('button', { name: '编辑' }).click()
  const renamedProject = `${projectName}-renamed`
  await page.getByLabel('编辑项目名称').fill(renamedProject)
  await page.getByLabel('编辑项目描述').fill('saved browser description')
  await page.getByRole('button', { name: '保存' }).click()
  projectRow = page.locator('article.row-card').filter({ hasText: renamedProject })
  await expect(projectRow).toContainText('saved browser description')
  await page.reload()
  await expect(projectRow).toBeVisible()

  await page.goto('/training')
  await expect(projectRow).toBeVisible()
  await page.goBack()
  await expect(projectRow).toBeVisible()
  await page.goForward()
  await expect(projectRow).toBeVisible()

  const archiveResponse = page.waitForResponse(response => response.url().endsWith(`/api/v1/projects/${createdProject.id}/archive`))
  await projectRow.getByRole('button', { name: '归档' }).click()
  expect((await archiveResponse).status()).toBe(200)
  await expect(projectRow).toContainText('已归档')
  await expect(projectRow.getByRole('button', { name: '归档' })).toBeDisabled()
  await page.reload()
  await expect(projectRow).toContainText('已归档')
  const repeatedArchive = await sameOrigin(page, `/projects/${createdProject.id}/archive`, { method: 'POST' })
  expect(repeatedArchive.status).toBe(200)
  const archivedJob = await sameOrigin(page, `/projects/${createdProject.id}/jobs`, {
    method: 'POST',
    body: { kind: 'dataset_check', params: { dataset_id: '00000000-0000-4000-8000-000000000001' } },
    headers: { 'Idempotency-Key': 'archived-project-browser-check' },
  })
  expect(archivedJob.status).toBe(409)
  expect((archivedJob.body as { error: { code: string } }).error.code).toBe('PROJECT_ARCHIVED')

  const ordinarySession = await contextPage(browser, root)
  await login(ordinarySession.page, user)
  await expect(ordinarySession.page.getByRole('heading', { name: '用户管理' })).toHaveCount(0)
  await expect(ordinarySession.page.getByText(renamedProject, { exact: true })).toHaveCount(0)
  expect((await sameOrigin(ordinarySession.page, '/admin/users')).status).toBe(403)
  expect((await sameOrigin(ordinarySession.page, `/projects/${createdProject.id}`)).status).toBe(404)
  expect((await sameOrigin(ordinarySession.page, `/projects/${createdProject.id}`, {
    method: 'PATCH', body: { description: 'must not change' },
  })).status).toBe(404)
  expect((await sameOrigin(ordinarySession.page, `/projects/${createdProject.id}/archive`, { method: 'POST' })).status).toBe(404)

  await userRow.getByRole('button', { name: '禁用' }).click()
  await expect(userRow).toContainText('账号已禁用')
  await ordinarySession.page.reload()
  await expect(ordinarySession.page.getByRole('heading', { name: '登录工作区' })).toBeVisible()
  await ordinarySession.page.getByLabel('用户名', { exact: true }).fill(user.username)
  await ordinarySession.page.getByLabel('密码', { exact: true }).fill(user.password)
  await ordinarySession.page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(ordinarySession.page.getByRole('alert')).toHaveText('Username or password is incorrect')
  await userRow.getByRole('button', { name: '启用' }).click()
  await expect(userRow).toContainText('账号已启用')
  await ordinarySession.page.reload()
  await expect(ordinarySession.page.getByRole('heading', { name: '登录工作区' })).toBeVisible()
  await ordinarySession.context.close()

  const currentSession = await contextPage(browser, root)
  const otherSession = await contextPage(browser, root)
  await login(currentSession.page, user)
  await login(otherSession.page, user)
  const beforeCookies = await currentSession.context.cookies(root)
  expect(beforeCookies.find(cookie => cookie.name === 'edgevision_session')?.httpOnly).toBe(true)
  expect(beforeCookies.find(cookie => cookie.name === 'edgevision_csrf')?.httpOnly).toBe(false)
  await currentSession.page.getByLabel('当前密码').fill(`${user.password}-wrong`)
  await currentSession.page.getByLabel('新密码').fill(rotatedPassword)
  await currentSession.page.getByRole('button', { name: '修改密码' }).click()
  await expect(currentSession.page.getByText('Current password is incorrect')).toBeVisible()
  await currentSession.page.getByLabel('当前密码').fill(user.password)
  await currentSession.page.getByRole('button', { name: '修改密码' }).click()
  await expect(currentSession.page.getByText('密码已更新，当前会话已安全轮换。')).toBeVisible()
  const afterCookies = await currentSession.context.cookies(root)
  expect(afterCookies.find(cookie => cookie.name === 'edgevision_session')?.value).not.toBe(beforeCookies.find(cookie => cookie.name === 'edgevision_session')?.value)
  expect(afterCookies.find(cookie => cookie.name === 'edgevision_csrf')?.value).not.toBe(beforeCookies.find(cookie => cookie.name === 'edgevision_csrf')?.value)
  await currentSession.page.reload()
  await expect(currentSession.page.getByRole('heading', { name: '项目工作区' })).toBeVisible()
  await otherSession.page.reload()
  await expect(otherSession.page.getByRole('heading', { name: '登录工作区' })).toBeVisible()
  await otherSession.context.close()

  const ordinaryProjectName = `ordinary-project-${Date.now()}`
  const ordinaryCreate = currentSession.page.waitForResponse(response => response.url().endsWith('/api/v1/projects') && response.request().method() === 'POST')
  await currentSession.page.getByLabel('项目名称').fill(ordinaryProjectName)
  await currentSession.page.getByLabel('描述', { exact: true }).fill('owned by ordinary user')
  await currentSession.page.getByRole('button', { name: '创建项目' }).click()
  expect((await ordinaryCreate).status()).toBe(201)
  await expect(currentSession.page.locator('article.row-card').filter({ hasText: ordinaryProjectName }).getByText(ordinaryProjectName, { exact: true })).toBeVisible()
  const logoutResponse = currentSession.page.waitForResponse(response => response.url().endsWith('/api/v1/auth/logout'))
  await currentSession.page.getByRole('button', { name: '退出' }).click()
  expect((await logoutResponse).status()).toBe(204)
  await currentSession.page.reload()
  await expect(currentSession.page.getByRole('heading', { name: '登录工作区' })).toBeVisible()
  await currentSession.page.getByLabel('用户名', { exact: true }).fill(user.username)
  await currentSession.page.getByLabel('密码', { exact: true }).fill(user.password)
  await currentSession.page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(currentSession.page.getByRole('alert')).toHaveText('Username or password is incorrect')
  await currentSession.page.getByLabel('用户名', { exact: true }).fill(user.username)
  await currentSession.page.getByLabel('密码', { exact: true }).fill(rotatedPassword)
  await currentSession.page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(currentSession.page.locator('article.row-card').filter({ hasText: ordinaryProjectName }).getByText(ordinaryProjectName, { exact: true })).toBeVisible()
  await currentSession.context.close()
})

test('375px keyboard flow remains usable without horizontal overflow', async ({ browser, baseURL }) => {
  const { admin } = fixtures()
  const context = await browser.newContext({
    baseURL: baseURL as string,
    viewport: { width: 375, height: 812 },
    locale: 'zh-CN',
    reducedMotion: 'reduce',
  })
  const page = await context.newPage()
  await page.goto('/')
  const username = page.getByLabel('用户名', { exact: true })
  const password = page.getByLabel('密码', { exact: true })
  await username.focus()
  await username.fill(admin.username)
  await page.keyboard.press('Tab')
  await expect(password).toBeFocused()
  await password.fill(admin.password)
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name: '项目工作区' })).toBeVisible()

  const longName = `mobile-${'x'.repeat(120)}`
  await page.getByLabel('项目名称').fill(longName)
  await page.getByLabel('描述', { exact: true }).fill('keyboard-created project')
  await page.getByLabel('描述', { exact: true }).press('Enter')
  const mobileProjectRow = page.locator('article.row-card').filter({ hasText: longName })
  await expect(mobileProjectRow.getByText(longName, { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)

  await page.goto('/projects')
  await page.goto('/training')
  await page.goBack()
  await expect(page).toHaveURL(/\/projects$/)
  await page.goForward()
  await expect(page).toHaveURL(/\/training$/)
  const logout = page.getByRole('button', { name: '退出' })
  await logout.focus()
  const logoutResponse = page.waitForResponse(response => response.url().endsWith('/api/v1/auth/logout'))
  await page.keyboard.press('Enter')
  expect((await logoutResponse).status()).toBe(204)
  await expect(page.getByRole('heading', { name: '登录工作区' })).toBeVisible()
  await context.close()
})
