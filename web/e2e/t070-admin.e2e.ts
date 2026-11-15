import { expect, test, type Page } from '@playwright/test'
function required(name: string) { const value=process.env[name]; if (!value) throw new Error('Missing isolated fixture'); return value }
async function login(page:Page, username:string,password:string) {
 await page.goto('/'); await page.getByLabel('用户名',{exact:true}).fill(username); await page.getByLabel('密码',{exact:true}).fill(password)
 await page.getByRole('button',{name:'登录',exact:true}).click(); await expect(page.getByRole('heading',{name:'项目工作区'})).toBeVisible()
}
async function request(page:Page,path:string,body?:unknown) {
 return page.evaluate(async({path,body})=>{
  const csrf=document.cookie.split(';').map(x=>x.trim()).find(x=>x.startsWith('edgevision_csrf='))?.slice('edgevision_csrf='.length)
  const response=await fetch('/api/v1'+path,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:body===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':decodeURIComponent(csrf??'')},body:body===undefined?undefined:JSON.stringify(body)})
  return {status:response.status,body:await response.json()}
 },{path,body})
}
test('administrator reads another user task through real global listing while user is denied',async({page,browser,baseURL})=>{
 await login(page,required('EDGEVISION_E2E_ADMIN_USERNAME'),required('EDGEVISION_E2E_ADMIN_PASSWORD'))
 const name='admin-task-member-'+Date.now(), password=required('EDGEVISION_E2E_USER_PASSWORD')
 expect((await request(page,'/admin/users',{username:name,password,role:'user'})).status).toBe(201)
 const context=await browser.newContext({baseURL}); const member=await context.newPage()
 try {
  await login(member,name,password)
  expect((await request(member,'/admin/jobs')).status).toBe(403)
  await expect(member.getByRole('region',{name:'管理员全局任务'})).toHaveCount(0)
  const created=await request(member,'/projects',{name:'owned-admin-check'}); expect(created.status).toBe(201)
  await member.reload(); await member.getByLabel('所属项目').selectOption(created.body.id)
  await member.getByLabel('受控 YOLO ZIP').setInputFiles(required('EDGEVISION_E2E_DATASET_ZIP'))
  await member.getByRole('button',{name:'上传新快照'}).click()
  const row=member.locator('.dataset-row').filter({hasText:'tiny-dataset'})
  await expect(row).toContainText('pending')
  const accepted=member.waitForResponse(r=>r.url().endsWith('/check')&&r.request().method()==='POST')
  await row.getByRole('button',{name:'开始校验'}).click(); const response=await accepted; expect(response.status()).toBe(202)
  const task=await response.json() as {job_id:string}
  await page.getByRole('navigation', {name:'工作区导航'}).getByRole('button', {name:'管理',exact:true}).click()
  const panel=page.getByRole('region',{name:'管理员全局任务'})
  await panel.getByRole('button',{name:'刷新任务'}).click()
  const globalRow=panel.locator('article').filter({hasText:task.job_id}); await expect(globalRow).toContainText(created.body.id)
  await globalRow.getByRole('button',{name:'查看',exact:true}).click()
  const detail=panel.getByRole('region',{name:'全局任务详情'}); await expect(detail).toContainText(task.job_id)
  await expect(row).toContainText('ready',{timeout:20000})
  await detail.getByRole('button',{name:'刷新详情'}).click(); await expect(detail).toContainText('succeeded')
  await expect(detail.getByLabel('全局任务日志')).toContainText('Dataset validation passed')
  await detail.getByRole('button',{name:'关闭详情'}).click(); await expect(detail).toHaveCount(0)
  await page.reload(); await page.getByRole('navigation', {name:'工作区导航'}).getByRole('button', {name:'管理',exact:true}).click(); await expect(panel.locator('article').filter({hasText:task.job_id})).toBeVisible()
  await page.setViewportSize({width:375,height:812}); expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
 } finally { await context.close() }
})
