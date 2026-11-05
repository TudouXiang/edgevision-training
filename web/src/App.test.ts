// @vitest-environment happy-dom

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App.vue'
import { datasetApi } from './api'

const admin = { id: '00000000-0000-4000-8000-000000000001', username: 'root', role: 'admin', is_active: true, created_at: '2026-11-04T00:00:00Z' }
const emptyPage = { items: [], total: 0, page: 1, page_size: 20 }
const features = Object.fromEntries(['auth', 'projects', 'datasets', 'training_cpu', 'training_cuda', 'events', 'models', 'onnx_export', 'pt_inference', 'onnx_inference', 'deployment', 'rknn'].map(key => [key, { available: key === 'auth' || key === 'projects', reason_code: null, reason: null, detected_version: null }]))

function json(body: unknown, status = 200) {
  return new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function error(status: number, code: string, message: string) {
  return json({ error: { code, message } }, status)
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}

async function settle() {
  await flushPromises()
  await new Promise(resolve => setTimeout(resolve, 0))
  await flushPromises()
}

afterEach(() => { vi.unstubAllGlobals(); document.cookie = 'edgevision_csrf=; Max-Age=0; path=/' })

describe('authenticated workspace state', () => {
  it('loads second pages and ignores page two after a newer refresh', async () => {
    const projects = Array.from({ length: 21 }, (_, index) => ({
      id: `00000000-0000-4000-8000-${String(index + 10).padStart(12, '0')}`,
      owner_id: admin.id, name: `project-${index + 1}`, description: '', archived_at: null,
      created_at: '2026-11-04T00:00:00Z', updated_at: '2026-11-04T00:00:00Z',
    }))
    const users = Array.from({ length: 21 }, (_, index) => ({ ...admin, id: `10000000-0000-4000-8000-${String(index + 10).padStart(12, '0')}`, username: `user-${index + 1}`, role: 'user' }))
    const stalePage = deferred<Response>()
    let projectPageTwoReads = 0
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (/\/projects\/[^/]+\/jobs\?/.test(url)) return Promise.resolve(json(emptyPage))
      if (url.endsWith('/health/live')) return Promise.resolve(json({ status: 'ok', service: 'api' }))
      if (url.endsWith('/health/ready')) return Promise.resolve(json({ status: 'ready', database: 'migrated', storage: 'available' }))
      if (url.endsWith('/capabilities')) return Promise.resolve(json({ schema_version: 1, features }))
      if (url.endsWith('/auth/me')) return Promise.resolve(json(admin))
      if (url.includes('/projects?page=2')) {
        projectPageTwoReads += 1
        return projectPageTwoReads === 1
          ? Promise.resolve(json({ items: projects.slice(20), total: 21, page: 2, page_size: 20 }))
          : stalePage.promise
      }
      if (url.includes('/projects?page=1')) return Promise.resolve(json({ items: projects.slice(0, 20), total: 21, page: 1, page_size: 20 }))
      if (url.includes('/admin/users?page=2')) return Promise.resolve(json({ items: users.slice(20), total: 21, page: 2, page_size: 20 }))
      if (url.includes('/admin/users?page=1')) return Promise.resolve(json({ items: users.slice(0, 20), total: 21, page: 1, page_size: 20 }))
      throw new Error(`unhandled ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(App)
    await settle()
    await wrapper.findAll('button').find(button => button.text() === '加载更多项目')!.trigger('click')
    await wrapper.findAll('button').find(button => button.text() === '加载更多用户')!.trigger('click')
    await settle()
    expect(wrapper.text()).toContain('project-21')
    expect(wrapper.text()).toContain('user-21')
    expect(wrapper.text()).toContain('已显示 21 / 21')

    await wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click')
    await settle()
    await wrapper.findAll('button').find(button => button.text() === '加载更多项目')!.trigger('click')
    await wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click')
    await settle()
    stalePage.resolve(json({ items: [{ ...projects[20], name: 'stale-page-two' }], total: 21, page: 2, page_size: 20 }))
    await settle()
    expect(wrapper.text()).not.toContain('stale-page-two')
    expect(wrapper.text()).toContain('已显示 20 / 21')
  })

  it('invalidates late responses, clears drafts, and keeps health/stage status', async () => {
    document.cookie = 'edgevision_csrf=test-csrf; path=/'
    const lateProjects = deferred<Response>()
    let projectReads = 0
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (/\/projects\/[^/]+\/jobs\?/.test(url)) return Promise.resolve(json(emptyPage))
      if (url.endsWith('/health/live')) return Promise.resolve(json({ status: 'ok', service: 'api' }))
      if (url.endsWith('/health/ready')) return Promise.resolve(json({ status: 'ready', database: 'migrated', storage: 'available' }))
      if (url.endsWith('/capabilities')) return Promise.resolve(json({ schema_version: 1, features }))
      if (url.endsWith('/auth/me')) return Promise.resolve(json(admin))
      if (url.includes('/projects?page=')) {
        projectReads += 1
        return projectReads === 2 ? lateProjects.promise : Promise.resolve(json(emptyPage))
      }
      if (url.includes('/admin/users?page=')) return Promise.resolve(json({ ...emptyPage, items: [admin], total: 1 }))
      if (url.endsWith('/auth/logout') && init?.method === 'POST') return Promise.resolve(json(null, 204))
      if (url.endsWith('/auth/login') && init?.method === 'POST') return Promise.resolve(json(admin))
      throw new Error(`unhandled ${init?.method ?? 'GET'} ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(App)
    await settle()
    expect(wrapper.text()).toContain('项目工作区')
    expect(wrapper.text()).toContain('API 已响应')
    expect(wrapper.text()).toContain('数据集 · 未实现')

    const projectInputs = wrapper.findAll('.grid-form input')
    await projectInputs[0].setValue('secret project draft')
    const adminInputs = wrapper.findAll('.admin-create input')
    await adminInputs[0].setValue('draft-user')
    await adminInputs[1].setValue('draft-password-123')
    const refresh = wrapper.findAll('button').find(button => button.text() === '刷新')!
    await refresh.trigger('click')
    const logout = wrapper.findAll('button').find(button => button.text() === '退出')!
    await logout.trigger('click')
    await settle()
    expect(wrapper.text()).toContain('登录工作区')

    const loginInputs = wrapper.findAll('.login-card input')
    await loginInputs[0].setValue('root')
    await loginInputs[1].setValue('admin-password-123')
    await wrapper.find('.login-card form').trigger('submit')
    await settle()
    lateProjects.resolve(error(401, 'SESSION_INVALID', 'old session expired'))
    await settle()
    expect(wrapper.text()).toContain('项目工作区')
    expect(wrapper.text()).not.toContain('old session expired')
    expect(wrapper.html()).not.toContain('draft-password-123')
    expect((wrapper.findAll('.admin-create input')[0].element as HTMLInputElement).value).toBe('')
    expect((wrapper.findAll('.admin-create input')[1].element as HTMLInputElement).value).toBe('')
    expect((wrapper.findAll('.grid-form input')[0].element as HTMLInputElement).value).toBe('')
    expect(wrapper.findAll('button').find(button => button.text() === '刷新')!.attributes('disabled')).toBeUndefined()
  })

  it('surfaces uncertain server logout instead of claiming success', async () => {
    const logoutResponse = deferred<Response>()
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (/\/projects\/[^/]+\/jobs\?/.test(url)) return Promise.resolve(json(emptyPage))
      if (url.endsWith('/health/live')) return Promise.resolve(json({ status: 'ok', service: 'api' }))
      if (url.endsWith('/health/ready')) return Promise.resolve(json({ status: 'ready', database: 'migrated', storage: 'available' }))
      if (url.endsWith('/capabilities')) return Promise.resolve(json({ schema_version: 1, features }))
      if (url.endsWith('/auth/me')) return Promise.resolve(json(admin))
      if (url.includes('/projects?page=')) return Promise.resolve(json(emptyPage))
      if (url.includes('/admin/users?page=')) return Promise.resolve(json(emptyPage))
      if (url.endsWith('/auth/logout') && init?.method === 'POST') return logoutResponse.promise
      throw new Error(`unhandled ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(App)
    await settle()
    await wrapper.findAll('button').find(button => button.text() === '退出')!.trigger('click')
    await flushPromises()
    expect(wrapper.find('.login-card button[type="submit"]').attributes('disabled')).toBeDefined()
    logoutResponse.reject(new Error('offline'))
    await settle()
    expect(wrapper.text()).toContain('登录工作区')
    expect(wrapper.text()).toContain('服务器退出失败，会话可能仍有效')
  })

  it('clears the workspace when password change reports an invalid session', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (/\/projects\/[^/]+\/jobs\?/.test(url)) return Promise.resolve(json(emptyPage))
      if (url.endsWith('/health/live')) return Promise.resolve(json({ status: 'ok', service: 'api' }))
      if (url.endsWith('/health/ready')) return Promise.resolve(json({ status: 'ready', database: 'migrated', storage: 'available' }))
      if (url.endsWith('/capabilities')) return Promise.resolve(json({ schema_version: 1, features }))
      if (url.endsWith('/auth/me')) return Promise.resolve(json(admin))
      if (url.includes('/projects?page=')) return Promise.resolve(json(emptyPage))
      if (url.includes('/admin/users?page=')) return Promise.resolve(json(emptyPage))
      if (url.endsWith('/auth/change-password') && init?.method === 'POST') return Promise.resolve(error(401, 'SESSION_INVALID', 'Session expired'))
      throw new Error(`unhandled ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(App)
    await settle()
    const fields = wrapper.findAll('input[type="password"]')
    await fields[0].setValue('admin-password-123')
    await fields[1].setValue('new-password-123')
    await fields[0].element.closest('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await settle()
    expect(wrapper.text()).toContain('登录工作区')
    expect(wrapper.text()).toContain('Session expired')
  })
})

describe('dataset upload client', () => {
  it('lets the browser set the multipart boundary and sends CSRF', async () => {
    document.cookie = 'edgevision_csrf=dataset-csrf; path=/'
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      expect(init?.method).toBe('POST')
      expect(init?.body).toBeInstanceOf(FormData)
      const headers = new Headers(init?.headers)
      expect(headers.has('Content-Type')).toBe(false)
      expect(headers.get('X-CSRF-Token')).toBe('dataset-csrf')
      const body = init?.body as FormData
      expect((body.get('file') as File).name).toBe('tiny.zip')
      return Promise.resolve(json({
        id: '20000000-0000-4000-8000-000000000001', project_id: '10000000-0000-4000-8000-000000000001',
        name: 'tiny', state: 'pending', version: 1, sha256: '0'.repeat(64), size_bytes: 3,
        classes: [], counts: null, created_at: '2026-11-04T00:00:00Z',
      }, 201))
    })
    vi.stubGlobal('fetch', fetchMock)
    const result = await datasetApi.upload(
      '10000000-0000-4000-8000-000000000001',
      new File([new Uint8Array([1, 2, 3])], 'tiny.zip', { type: 'application/zip' }),
    )
    expect(result.state).toBe('pending')
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('project switching clears stale upload state and ignores its late response', async () => {
    document.cookie = 'edgevision_csrf=dataset-csrf; path=/'
    const firstProject = { id: '30000000-0000-4000-8000-000000000001', owner_id: admin.id, name: 'first', description: '', archived_at: null, created_at: admin.created_at, updated_at: admin.created_at }
    const secondProject = { ...firstProject, id: '30000000-0000-4000-8000-000000000002', name: 'second' }
    const lateUpload = deferred<Response>()
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (/\/projects\/[^/]+\/jobs\?/.test(url)) return Promise.resolve(json(emptyPage))
      if (url.endsWith('/health/live')) return Promise.resolve(json({ status: 'ok', service: 'api' }))
      if (url.endsWith('/health/ready')) return Promise.resolve(json({ status: 'ready', database: 'migrated', storage: 'available' }))
      if (url.endsWith('/capabilities')) return Promise.resolve(json({ schema_version: 1, features }))
      if (url.endsWith('/auth/me')) return Promise.resolve(json(admin))
      if (url.includes('/projects?page=')) return Promise.resolve(json({ ...emptyPage, items: [firstProject, secondProject], total: 2 }))
      if (url.includes('/admin/users?page=')) return Promise.resolve(json(emptyPage))
      if (url.includes(`/projects/${firstProject.id}/datasets`) && init?.method === 'POST') return lateUpload.promise
      if (url.includes(`/projects/${firstProject.id}/datasets?`)) return Promise.resolve(json(emptyPage))
      if (url.includes(`/projects/${secondProject.id}/datasets?`)) return Promise.resolve(json(emptyPage))
      throw new Error(`unhandled ${init?.method ?? 'GET'} ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(App)
    await settle()
    const picker = wrapper.get('select').findAll('option').some(option => option.text() === 'first')
      ? wrapper.findAll('select').find(select => select.findAll('option').some(option => option.text() === 'first'))!
      : wrapper.get('select')
    await picker.setValue(firstProject.id)
    await settle()
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [new File([new Uint8Array([1])], 'tiny.zip', { type: 'application/zip' })] })
    await input.trigger('change')
    await wrapper.get('form.dataset-upload').trigger('submit')
    await flushPromises()
    expect(wrapper.get('form.dataset-upload button[type="submit"]').text()).toContain('上传中')
    await picker.setValue(secondProject.id)
    await settle()
    expect(wrapper.get('input[type="file"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('form.dataset-upload button[type="submit"]').text()).toContain('上传新快照')
    lateUpload.resolve(json({
      id: '40000000-0000-4000-8000-000000000001', project_id: firstProject.id, name: 'tiny', state: 'pending',
      version: 1, sha256: '0'.repeat(64), size_bytes: 1, classes: [], counts: null, created_at: admin.created_at,
    }, 201))
    await settle()
    expect(wrapper.text()).toContain('这个项目还没有数据集')
    expect(wrapper.text()).not.toContain('tiny · v1')
  })
})
