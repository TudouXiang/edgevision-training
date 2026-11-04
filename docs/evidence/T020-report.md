# T020 任务交付记录

> 后续更新：T020 已完成 Linux CI 真实浏览器与独立验收，见 [最终补证记录](T020-browser-acceptance-2026-11-04.md)。下文保留当时的状态与证据，不改写历史 NOT_RUN。

任务 ID / 状态：T020 / `review_required`

基线：`dff9ad1fc92e9ce43b135138df18795106d4bf89`（`main`）；开始编辑前 `git status --short` 为空。环境：Linux、Python 3.12.14、uv 0.13.5、Node 24.22.1、npm 11.9.0。执行日期：2026-11-04 UTC。

## 范围与决策

本候选完成真实 Argon2id 密码、opaque server session、Origin/CSRF、显式管理员初始化、管理员用户管理、项目 owner/编辑/归档、现有派生资源权限前置守卫和最小真实 Vue 页面。复用 `0002_foundation` 与既有 DTO，没有数据库迁移、注册/JWT/邮件/第三方登录，也没有进入 T030 数据集或训练/模型/RKNN 实现。依赖与 Cookie/Origin 决策见 ADR 0007。

主要文件：

- `backend/app/security.py`、`services.py`、`main.py`：密码、会话、同写事务鉴权、用户/项目实现及派生资源守卫。
- `backend/app/admin_cli.py`、`scripts/dev.py`：交互式首管理员入口；聚合检查增加前端测试。
- `backend/app/config.py`：明确允许 Origin、Secure Cookie 和 TTL 的失败关闭配置。
- `backend/tests/test_auth_projects.py`：T020 API/CLI/权限集成测试。
- `web/src/App.vue`、`api.ts`、`style.css`、`App.test.ts`：真实 UI、生成类型、异步会话隔离、分页与回归测试。
- `contracts/`、`docs/api.md`、`docs/schema.md`、`docs/status.md`：生成契约和状态同步。

公共成功 DTO 无变化；OpenAPI 新增实际错误响应说明，API 版本为 0.2.0。依赖新增锁定的 `argon2-cffi`；前端测试新增 Vitest、Vue Test Utils 和 happy-dom，仅为开发依赖。

## 编辑前基线

|检查|实际命令/操作|退出码|结果|
|---|---|---:|---|
|首次聚合入口|`python scripts/dev.py check`|127|预期环境缺口：`backend/.venv` 不存在；没有把未运行写成通过|
|隔离依赖|`UV_CACHE_DIR=/tmp/uv-cache npm_config_cache=/tmp/npm-cache python scripts/install_deps.py`|0|依赖只进入 `backend/.venv`、`web/node_modules`；未装系统/模型/训练依赖|
|真实基线|`python scripts/dev.py check`|0|unittest 6+9、pytest 20、Vue build、contract-check 全部通过|

默认 uv/npm cache 指向只读 home，首次安装退出 2；改用 `/tmp` 项目执行缓存后成功。该调整没有改变系统依赖或产品配置。

## 最终自动验证

|检查|实际命令/操作|退出码|PASS/FAIL/NOT_RUN|实际现象|
|---|---|---:|---|---|
|T020 后端聚焦|`cd backend && .venv/bin/python -m pytest tests/test_auth_projects.py -q`|0|PASS|6 项通过|
|完整后端|`cd backend && .venv/bin/python -m pytest -q`|0|PASS|26 passed，另有 8 subtests；仅现有 Starlette/Alembic deprecation warning|
|前端状态/竞态/分页|`cd web && npm test`|0|PASS|Vitest 4/4；覆盖退出清理、迟到旧会话 401、退出失败、改密 401、21 条分页及刷新覆盖迟到 page 2|
|前端类型与构建|`cd web && npm run build`|0|PASS|vue-tsc 及 Vite 通过；1890 modules transformed|
|聚合入口|`python scripts/dev.py check`|0|PASS|unittest、26 pytest、4 Vitest、Vue build、OpenAPI 漂移检查依次通过|
|契约生成/漂移|`python scripts/dev.py contract-generate` 后聚合 `contract-check`|0|PASS|`contracts/openapi.json` 与 `contracts/generated/openapi.ts` 匹配当前 FastAPI/Pydantic|
|真实进程 HTTP|隔离 `TemporaryDirectory` 迁移，启动 `scripts/dev.py api`(18123) 与 `web`(15179)，用标准库 `urlopen` 探测后终止|0|PASS|`health/live` 200 JSON、`health/ready` 200 JSON、Vite `/` 200 HTML；测试 DB/进程已清理|
|差异卫生|`git diff --check`|0|PASS|无空白错误；无真实凭据、测试 DB、构建产物或模型纳入差异；测试文件只含明确隔离的虚构凭据|

测试账号、session 和数据库仅存在于 pytest `tmp_path` 或 HTTP 探针的临时目录。报告不记录原始密码/令牌内容。CLI 的 `main()` 已用 monkeypatch 的双次 getpass 输入覆盖并验证输出不含密码；真实终端手工输入没有单独执行。

## 验收结论

- 正确/错误密码、匿名、缺失/null/错误 Origin、无效 CSRF、畸形非 ASCII CSRF、HTTPS/Secure 配置失败关闭：PASS（自动测试）。
- Cookie 属性、数据库只存 token 哈希、过期/登出/撤销/禁用、改密撤销其他会话并轮换当前 session/CSRF：PASS（自动测试）。
- 重复用户名、普通用户拒绝管理接口、最后一个启用管理员保护、禁用用户撤销会话：PASS（自动测试）。
- 普通用户只列出自己的项目；他人项目及 Dataset/Job/log/metric/Artifact/download/cancel 统一 404；本人/管理员通过权限后未实现业务仍为 501：PASS（自动测试）。
- 项目创建/读取/编辑/幂等归档保留数据库记录；归档项目新 Job/上传守卫 409：PASS（自动测试）。
- A05：自动化覆盖为 PASS 候选；整体仍 `review_required`，因为真实浏览器补证未执行。

## 未执行、风险与回退

真实浏览器/视觉/键盘操作及截图：**NOT_RUN**。独立复核尝试本机 Chromium，浏览器在启动前因 `process_singleton_posix.cc socket() Operation not permitted` 崩溃；允许的升级重试结果相同。云浏览器访问工作区 Vite 地址得到 `ERR_CONNECTION_REFUSED`，属于隔离网络面。没有可用浏览器证据，因此不能把 T020 标为 accepted，也不能声称视觉验收通过。应在可访问该工作区端口的本机浏览器补登录、刷新、双击提交、退出、窄屏、键盘与历史导航。

未执行真实多进程禁用/写入竞态压力；实现以 `BEGIN IMMEDIATE` 同事务重查和集成测试为证，SQLite 高并发仍不是范围。HTTPS 只用 TestClient 验证配置/Cookie 属性，没有实际 TLS 部署。

## 浏览器 CI 源码补充（2026-11-04 UTC）

在既有失败证据之上增补了可重复的真实浏览器回归源码：锁定 `@playwright/test`，由 `scripts/e2e.py` 独占临时目录，执行真实 Alembic 迁移、通过测试入口生成随机管理员、启动真实 Uvicorn 与 Vite 同源代理，然后串行运行 Chromium 测试。覆盖错误/正确登录、刷新/退出、项目双提交守卫、编辑取消/保存、归档/重载、管理员建号/重复名/禁用/启用、改密会话轮换与其他会话撤销、普通用户所有权、375px 键盘和历史导航。失败报告使用白名单字段，不收集截图、trace、视频、请求/服务日志、数据库、Cookie 或凭据。

这没有改变产品 DTO、数据库迁移、正式启动链路或部署拓扑；更小但不足的方案是继续扩大 Vitest/fetch mock，因不能形成真实浏览器与真实服务证据而未采用。GitHub Actions 仅有 `contents: read`，对 feature push/PR 运行锁定依赖、原聚合检查和浏览器套件，失败只上传脱敏摘要。当前受限宿主只运行 `npm run test:e2e:list` 和 `python scripts/e2e.py --report-dir /tmp/edgevision-e2e-report --list`，均退出 0；后者实际完成临时迁移、管理员建立、API/Vite 同源 ready 探针和清理，但 `--list` 不启动 Chromium。因此真实浏览器结果仍为 **NOT_RUN**，原 NOT_RUN 记录不被覆盖。详细文件与复现命令见 [`T020-browser-ci-source-2026-11-04.md`](T020-browser-ci-source-2026-11-04.md)。

回退代码无需数据库 downgrade，但已有真实 Argon2id 用户时，不能回退到不识别该哈希的版本而不先做受审迁移。回退前应停 API、备份数据库；不要删除 sessions/projects 记录。T030 仍未放行。
