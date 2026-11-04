# T020 浏览器 CI 源码记录 · 2026-11-04 UTC

> 后续更新：T020 已完成 Linux CI 真实浏览器与独立验收，见 [最终补证记录](T020-browser-acceptance-2026-11-04.md)。下文保留当时的状态与证据，不改写历史 NOT_RUN。

任务 / 状态：T020 浏览器补证基础 / `review_required`。源码基线：`63199358f0a4d2c57457b90264e7cc03171b544a`；编辑前 `git status --short` 为空。当前记录只证明测试与 CI 源码及本机非浏览器编排，不声称 Chromium 已运行。

## 最小决策

- 产品范围、公共 API、数据库 schema、迁移和正式启动拓扑均不变。新增精确锁定的 `@playwright/test` 开发依赖、测试专用包装器和 GitHub Actions。
- 包装器只创建并删除自己拥有的临时目录；实际执行 `alembic upgrade head`，调用既有 `create_admin` 生成随机测试管理员，再启动真实 Uvicorn 与 Vite `/api/v1` 同源代理。账号、密码只存在于父进程内存和测试子进程环境，不进入命令行、源码、报告或正式启动。
- 浏览器用例不 mock/fulfill API 响应。串行单 worker、零 retry，避免共享数据库竞态掩盖失败。截图、trace、视频、HAR、storage state、服务日志和数据库均不生成失败附件。
- 自定义报告只允许静态用例标题、状态、耗时和源码位置。GitHub Actions 权限为 `contents: read`；官方 actions 固定到提交 SHA，失败只上传该脱敏 JSON/Markdown，保留 7 天。
- 未采用扩大 Vitest mock 的更小依赖方案，因为它不能证明真实 Cookie/CSRF、FastAPI、SQLite、Vite 代理和 Chromium 的端到端行为。未使用 `--with-deps` 自动改 runner 系统依赖；先在 `ubuntu-24.04` 托管 runner 验证现有浏览器运行库。

## 覆盖

1. 错误密码、正确登录、会话刷新和退出后刷新。
2. 项目创建的重复触发守卫、读取、编辑取消、保存、重载、归档保留、重复归档和归档后新任务拒绝。
3. 管理员创建普通用户、重复用户名、禁用撤销现有会话、禁用登录拒绝、重新启用但旧会话不复活。
4. 错误当前密码、正确改密、session/CSRF 同时轮换、其他浏览器会话撤销、旧密码拒绝和新密码登录。
5. 普通用户看不到管理 UI，管理 API 返回 403，他人项目详情返回 404；普通用户自己的项目在刷新和重新登录后保留。
6. 375px 视口通过 Tab/Enter 登录、Enter 建项目、长不换行名称无横向溢出、Back/Forward 路由和键盘退出。

## 本机实际检查

|检查|命令|退出码|结论|
|---|---|---:|---|
|Playwright 测试发现|`cd web && npm run test:e2e:list`|0|PASS；配置/测试/安全 reporter 可加载，发现 2 个用例，0 个用例实际执行|
|E2E TypeScript|`cd web && npm run typecheck:e2e`|0|PASS；Playwright config、2 个浏览器用例与脱敏 reporter 通过严格类型检查|
|临时迁移与服务编排发现|`python scripts/e2e.py --report-dir /tmp/edgevision-e2e-report-final --list`|0|PASS；发现 2 个用例；实际迁移、随机管理员、真实 API/Vite ready、Playwright 发现和清理；没有启动浏览器|
|完整原聚合检查|`python scripts/dev.py check`|0|PASS；unittest 6+9、pytest 26、Vitest 4、Vue 类型/构建、契约漂移检查全部通过|
|失败报告脱敏探针|临时无浏览器用例抛出含唯一 sentinel 的 Error，以 safe reporter 运行后对摘要递归 `grep`|0（探针本身预期退出 1）|PASS；摘要只记录失败用例、耗时及精确源码行列，未出现 sentinel、原始错误/stack/stdout/附件|
|CI YAML 静态解析|Python `yaml.safe_load(.github/workflows/t020-ci.yml)`|0|PASS；workflow 名和 `checks` job 可解析；不等于 GitHub Actions 实际执行|
|真实 Chromium|未执行；遵守既有宿主 socket 限制，不重试/绕过|—|NOT_RUN；等待分支发布后的托管 CI|

托管 CI 的原始 URL、commit SHA、runner 镜像与 Chromium 结果必须在发布后另行追加；源码存在或 `--list` 成功不能把 T020 写为 accepted，也不放行 T030。

## 首次发布的 workflow 校验失败与修正

已发布提交 `f550336d0245d7086cd82356aa1c10ba61bae763` 的 [GitHub Actions run `41779527773`](https://github.com/TudouXiang/edgevision-training/actions/runs/41779527773) 在创建 job 前立即失败，没有 runner、步骤或 Chromium 执行证据。原因由 GitHub 官方 context availability 表确认：`jobs.<job_id>.env` 只允许 `github, needs, strategy, matrix, vars, secrets, inputs`，不允许 `runner`，所以该位置的 `${{ runner.temp }}` 无效。

修正保留 job 级 `CI=true`，删除三个 job-env `runner.temp` 表达式；首个 `run` 步骤改用 runner 已提供的 `$RUNNER_TEMP`，把 `UV_CACHE_DIR`、`npm_config_cache` 和 `PLAYWRIGHT_BROWSERS_PATH` 写入 `$GITHUB_ENV`，供后续步骤使用。GitHub 官方说明 `$GITHUB_ENV` 写入在同一 job 的后续步骤生效；step 的 `run`/`with` 允许 `runner` context，因此失败产物步骤继续使用 `${{ runner.temp }}` 合法。修正尚未发布，真实 Chromium 仍为 **NOT_RUN**。

官方依据：[`Context availability`](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#context-availability)、[`runner.temp`](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#runner-context)、[`GITHUB_ENV`](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands#setting-an-environment-variable)。
