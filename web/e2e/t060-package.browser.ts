import { createHash } from 'node:crypto'
import { writeFile } from 'node:fs/promises'
import { expect, test, type Page } from '@playwright/test'
import type { components } from '../../contracts/generated/openapi'
type Artifact=components['schemas']['ArtifactPublic']
type Job=components['schemas']['JobPublic']
function required(name:string) { const value=process.env[name]; if (!value) throw new Error('Missing private package harness input'); return value }
async function inventory(page:Page, project:string, kind:'jobs'|'artifacts'):Promise<(Job|Artifact)[]> {
  const items:(Job|Artifact)[]=[]
  for(let index=1;index<=100;index++) {
    const response=await page.request.get(`/api/v1/projects/${encodeURIComponent(project)}/${kind}?page=${index}&page_size=100`)
    expect(response.status()).toBe(200)
    const body=await response.json();items.push(...body.items)
    if(items.length>=body.total)return items
    if(!body.items.length)break
  }
  throw new Error('Incomplete package inventory')
}
// Private fixed-lineage harness only. No login bypass, direct DB writes, probe,
// model execution or public artifact reporting happens in this browser suite.
test('real package UI creates one immutable ZIP and restores accepted identity',async({page,context})=>{
  test.setTimeout(135_000)
  const checkpoint=async(phase:string)=>{await writeFile(required('EDGEVISION_E2E_PACKAGE_PHASE_FILE'),JSON.stringify({phase}),{mode:0o600})}
  await checkpoint('ui_setup')
  expect(process.env.EDGEVISION_E2E_PACKAGE).toBe('1')
  const base=new URL(required('EDGEVISION_E2E_BASE_URL'))
  expect(['http:','https:']).toContain(base.protocol);expect(['127.0.0.1','localhost','[::1]']).toContain(base.hostname)
  const session:unknown=JSON.parse(required('EDGEVISION_E2E_PACKAGE_SESSION'))
  if(!session||typeof session!=='object'||Object.keys(session).sort().join(',')!=='edgevision_csrf,edgevision_session')throw new Error('Invalid private session')
  for(const name of ['edgevision_session','edgevision_csrf'] as const){
    const value=(session as Record<string,unknown>)[name]
    if(typeof value!=='string'||!value||/[\x00-\x20\x7f]/.test(value))throw new Error('Invalid private session')
    await context.addCookies([{name,value,url:base.origin,httpOnly:name==='edgevision_session',secure:base.protocol==='https:',sameSite:'Lax'}])
  }
  const project=required('EDGEVISION_E2E_PACKAGE_PROJECT_ID'),onnxId=required('EDGEVISION_E2E_PACKAGE_ONNX_ID')
  await checkpoint('ui_capabilities')
  const capabilities=await page.request.get('/api/v1/capabilities');expect(capabilities.status()).toBe(200)
  expect((await capabilities.json()).features.deployment.available).toBe(true)
  await checkpoint('ui_inventory')
  const artifacts=await inventory(page,project,'artifacts') as Artifact[]
  const onnx=artifacts.find(a=>a.id===onnxId)
  if(!onnx||onnx.kind!=='onnx')throw new Error('Missing verified ONNX')
  expect(onnx.project_id).toBe(project);expect(onnx.validation_state).toBe('passed')
  const source=await page.request.get(`/api/v1/jobs/${onnx.job_id}`);expect(source.status()).toBe(200)
  expect(await source.json()).toMatchObject({id:onnx.job_id,project_id:project,kind:'export_onnx',state:'succeeded'})
  const before=new Set((await inventory(page,project,'jobs')).map(job=>job.id))
  await page.goto('/deployment');await page.getByLabel('所属项目').selectOption(project)
  const panel=page.locator('.package-panel')
  await expect(panel).toContainText('不是开箱即用的离线包')
  await expect(panel.getByLabel('来源 ONNX').locator('option',{hasText:onnxId})).toHaveCount(1)
  await panel.getByLabel('来源 ONNX').selectOption(onnxId)
  await checkpoint('ui_submit')
  const button=panel.getByRole('button',{name:'创建独立部署包',exact:true});await expect(button).toBeEnabled()
  const accepted=page.waitForResponse(r=>r.url().endsWith(`/projects/${project}/jobs`)&&r.request().method()==='POST'&&r.request().postDataJSON()?.kind==='package')
  await button.evaluate((element:HTMLButtonElement)=>{element.click();element.click()})
  const response=await accepted;expect(response.status()).toBe(202);const receipt=await response.json()
  await checkpoint('ui_result')
  await expect(panel.locator('h3')).toContainText('succeeded',{timeout:60_000})
  await expect(panel).toContainText(receipt.job_id);await expect(panel).toContainText('已读取最终日志')
  const jobs=await inventory(page,project,'jobs') as Job[]
  const created=jobs.filter(job=>!before.has(job.id)&&job.kind==='package')
  expect(created).toHaveLength(1);expect(created[0]).toMatchObject({id:receipt.job_id,state:'succeeded',project_id:project})
  expect(created[0]!.package?.onnx_artifact_id).toBe(onnxId)
  const outputs=(await inventory(page,project,'artifacts') as Artifact[]).filter(a=>a.job_id===receipt.job_id&&a.kind==='deployment_zip')
  expect(outputs).toHaveLength(1);const output=outputs[0]!
  if(output.kind!=='deployment_zip')throw new Error('Wrong output kind')
  expect(output.validation_state).toBe('passed');expect(output.project_id).toBe(project)
  expect(output.metadata.provenance).toMatchObject({job_id:receipt.job_id,project_id:project,onnx_artifact_id:onnxId,export_job_id:onnx.job_id,model_sha256:onnx.sha256})
  expect(output.metadata.validation_scope).toBe('trusted_model_fixed_package_integrity')
  expect(output.metadata.standalone_execution).toBe('not_run_for_this_artifact')
  expect(output.metadata.package_sha256).toBe(output.sha256);expect(output.metadata.package_size_bytes).toBe(output.size_bytes)
  await checkpoint('ui_download')
  const link=panel.getByRole('link',{name:/下载独立部署包/});await expect(link).toHaveCount(1)
  const event=page.waitForEvent('download');await link.click();const download=await event
  expect(await download.failure()).toBeNull();expect(download.suggestedFilename()).toMatch(/\.zip$/)
  const stream=await download.createReadStream();expect(stream).not.toBeNull()
  const hash=createHash('sha256');let size=0;for await(const chunk of stream!){size+=chunk.length;hash.update(chunk)}
  expect(size).toBe(output.size_bytes);expect(hash.digest('hex')).toBe(output.sha256);await download.delete()
  await checkpoint('ui_reload')
  await page.reload();await page.getByLabel('所属项目').selectOption(project)
  await panel.getByLabel('来源 ONNX').selectOption(onnxId)
  await expect(panel.getByRole('button',{name:'已提交打包',exact:true})).toBeDisabled()
  await panel.getByRole('button',{name:'查看已接收任务',exact:true}).click()
  await expect(panel.locator('h3')).toContainText('succeeded');await expect(panel).toContainText(receipt.job_id)
  await expect(panel.getByRole('link',{name:/下载独立部署包/})).toHaveCount(1)
  expect((await inventory(page,project,'jobs') as Job[]).filter(job=>!before.has(job.id)&&job.kind==='package').map(job=>job.id)).toEqual([receipt.job_id])
  await checkpoint('ui_offline');await context.setOffline(true)
  await expect(panel.getByRole('alert')).toContainText('将自动重试',{timeout:20_000})
  await checkpoint('ui_recovery');await context.setOffline(false)
  await expect(panel.getByRole('alert')).toHaveCount(0,{timeout:20_000})
  await expect(panel.locator('h3')).toContainText('succeeded')
  await checkpoint('ui_responsive');await page.setViewportSize({width:375,height:812})
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  await checkpoint('ui_complete')
})
