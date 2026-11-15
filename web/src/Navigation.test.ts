// @vitest-environment happy-dom
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App.vue'
const empty = { items: [], total: 0, page: 1, page_size: 20 }
const project = { id: 'p1', owner_id: 'u1', name: '视觉检测', description: '', archived_at: null }
const components = Object.fromEntries(['JobPanel','TrainingPanel','ExperimentComparisonPanel','ExportPanel','PackagePanel','InferencePanel','AdminJobsPanel'].map(name => [name, { template: `<section>${name}</section>` }]))
afterEach(() => vi.unstubAllGlobals())
async function setup(role = 'admin') {
  vi.stubGlobal('fetch', vi.fn(async (input) => {
    const url = String(input)
    const body = url.endsWith('/auth/me') ? { id:'u1', username:'tester', role }
      : url.endsWith('/capabilities') ? { features:{} }
      : url.includes('/health/') ? {status:'ready'}
      : url.includes('/projects?') ? {...empty, items:[project], total:1} : empty
    return new Response(JSON.stringify(body), { headers: {'Content-Type':'application/json'} })
  }))
  const wrapper = mount(App, { attachTo: document.body, global: { stubs: components } })
  await flushPromises()
  return wrapper
}
it('enters a project explicitly and separates workflow from administration', async () => {
  const w = await setup()
  expect(w.find('[aria-label="工作区导航"]').exists()).toBe(true)
  expect(w.find('.admin-create').isVisible()).toBe(false)
  await w.findAll('button').find(b => b.text() === '进入项目')!.trigger('click')
  await flushPromises()
  expect(w.find('[aria-label="项目流程"]').isVisible()).toBe(true)
  expect(w.find('.dataset-panel').isVisible()).toBe(true)
  await w.find('[aria-label="项目流程"]').findAll('button').find(b => b.text() === '训练')!.trigger('click')
  expect(w.find('.dataset-panel').isVisible()).toBe(false)
  expect(w.find('[data-workflow="training"]').isVisible()).toBe(true)
  await w.find('[aria-label="工作区导航"]').findAll('button').find(b => b.text() === '管理')!.trigger('click')
  expect(w.find('.admin-create').isVisible()).toBe(true)
  expect(w.find('[data-workflow="training"]').isVisible()).toBe(false)
  await w.findAll('button').find(b => b.text() === '项目工作区')!.trigger('click')
  expect(w.find('[data-workflow="training"]').isVisible()).toBe(true)
  const trainingElement = w.find('[data-workflow="training"] section').element
  await w.findAll('button').find(b => b.text() === '返回项目列表')!.trigger('click')
  expect(w.find('[data-workflow="training"] section').element).toBe(trainingElement)
  await w.findAll('button').find(b => b.text() === '进入项目')!.trigger('click')
  w.unmount()
})
it('does not expose administrator navigation to ordinary users', async () => {
  const w = await setup('user')
  expect(w.find('[aria-label="工作区导航"]').text()).not.toContain('管理')
  expect(w.find('.admin-create').exists()).toBe(false)
  w.unmount()
})
