# EdgeVision — 边缘视觉模型管理与部署平台

EdgeVision 当前以目标检测为首个可验证场景，面向轻量单机环境串起数据、训练、模型、ONNX 验证与部署生命周期；ONNX 是部署主线，RKNN 仅保留未验证的扩展边界，不冒充实机能力。本仓库已交付范围/存储/接口基线、API 与 Worker 骨架以及迁移/测试基础。T020 真实身份、管理员账号管理与项目闭环已通过独立审查及 Linux CI 真实浏览器验收；T030 受限数据集上传、版本记录与纯校验核心已通过独立审查和 Linux CI 三项真实浏览器回归；异步校验、训练、模型和部署仍明确未实现。状态见 `docs/status.md` 与 `docs/evidence/T020-browser-acceptance-2026-11-04.md`。

## 目录

- `docs/`：范围、架构、环境、接口、表、存储、模型、验收、ADR、证据、T000–T070 任务。
- `backend/`：FastAPI 健康/就绪接口、显式 501 占位、独立 Worker 入口、Alembic 迁移。
- `web/`：Vue 3/TypeScript 最小状态页面，只报告真实 API 状态。
- `contracts/openapi.json`、`contracts/generated/openapi.ts`：从 FastAPI OpenAPI 生成的公共契约和前端类型；`contracts/api.ts` 临时桥接已移除。
- `scripts/install_deps.py`：Linux/Windows 共用的项目依赖安装与预检；`scripts/dev.py`：共用的检查、启动、迁移、生成入口。`scripts/dev.sh` 保留为 Linux/Bash 兼容包装。
- `reference/edgevision-studio-frontend.zip`：既有演示前端**原样保留**，含虚构数据，不能用于产品运行或验收。

## Linux / Windows 开发安装

在仓库根目录运行。先自行准备 **Python 3.11+、[uv](https://docs.astral.sh/uv/getting-started/installation/)、[Node.js](https://nodejs.org/en/download) 22.13+（含 npm）**，确保命令在 PATH 中；SQLite 由 Python 标准库提供。脚本不会安装系统软件、下载 Python 解释器、模型、Torch 或 RKNN。后端依赖进入 `backend/.venv`，前端依赖进入 `web/node_modules`。现有 `backend/uv.lock` 已纳入 Git 基线，安装脚本以 `--locked` 检查，不应绕过锁文件。`npm ci` 使用现有 `web/package-lock.json`，并会清理现有 `node_modules`。切换操作系统时重新安装这些本地依赖，不复制旧系统的 `.venv` 或 `node_modules`。依赖下载需要能访问对应包源。

Linux（Bash）：

```bash
python3 scripts/install_deps.py --check
python3 scripts/install_deps.py
python3 scripts/dev.py doctor
```

Windows（PowerShell，`py -3` 应选到 3.11 或更新版本；也可用相应的 `python` 命令）：

```powershell
py -3 scripts\install_deps.py --check
py -3 scripts\install_deps.py
py -3 scripts\dev.py doctor
```

仅装一侧依赖可分别加 `--backend-only` 或 `--web-only`；`--check` 只检查前置工具与将执行的命令，不安装。安装中某一步失败即返回非零，输出不代表后续步骤已完成。训练、ONNX 和硬件依赖须按后续任务及实际设备单独核验。

## 初始化与启动

如已有旧版 `0001` 数据库，**先停 API/Worker、做一致性备份，并在副本上验证 `0002_foundation`**；不要对唯一数据副本直接试迁移。全新开发目录才直接运行下面的迁移命令。

Linux：

```bash
python3 scripts/dev.py migrate
python3 scripts/dev.py init-admin   # 交互式输入并确认密码，不把密码放在命令行
python3 scripts/dev.py api
# 另开终端：python3 scripts/dev.py worker
# 再开终端：python3 scripts/dev.py web
```

Windows PowerShell：

```powershell
py -3 scripts\dev.py migrate
py -3 scripts\dev.py init-admin
py -3 scripts\dev.py api
# 另开终端：py -3 scripts\dev.py worker
# 再开终端：py -3 scripts\dev.py web
```

浏览器访问 `http://127.0.0.1:5173/`；API 直接地址为 `http://127.0.0.1:8000/api/v1/health/live`，根路径 `/` 返回 404。前端从同源 `/api/v1` 访问服务，由 Vite 代理至 127.0.0.1:8000。端口占用时可设置 `EDGEVISION_DEV_API_PORT` 和 `EDGEVISION_DEV_WEB_PORT`。`EDGEVISION_ADMIN_USERNAME` 可覆盖初始化命令默认显示名；密码只从交互式隐藏输入读取。

身份配置默认只允许 `http://127.0.0.1` / `localhost` 的 5173、8000 开发 Origin。部署时用逗号分隔的 `EDGEVISION_ALLOWED_ORIGINS` 明确列出浏览器 Origin；非本机 Origin 必须是 HTTPS，并同时设置 `EDGEVISION_COOKIE_SECURE=true`，否则身份接口按失败关闭返回 503。`EDGEVISION_SESSION_TTL_SECONDS` 可设为 300–604800 秒，默认 43200。修改请求必须携带同源 Origin 与浏览器从 CSRF Cookie 读取的 `X-CSRF-Token`。

Worker 遇到不明遗留 running/cancelling 任务会停止领取并返回 4，不会静默重训。真实任务的进程树清理与重启验证仍属 T040。

检查/契约生成（把 `python3 scripts/dev.py` 换为 Windows 的 `py -3 scripts\dev.py`）：

```bash
python3 scripts/dev.py contract-generate
python3 scripts/dev.py contract-check
python3 scripts/dev.py check
```

`contract-generate` 从 FastAPI OpenAPI 生成 TS；`contract-check` 不修改跟踪产物。`check` 包括纯契约/脚本测试、后端 pytest、前端构建和契约漂移检查。兼容的 Bash 入口仍可使用 `bash scripts/dev.sh <命令>`。Windows 本机的运行结果见 `docs/evidence/T010-windows-2026-09-28.md`；此前 Linux 容器缺依赖的结论只适用于当时环境。

T020 身份/项目与 T030 上传/pending 版本的真实浏览器回归使用锁定的 Playwright/Chromium，并且只连接测试入口创建的临时迁移数据库。先安装项目依赖和与锁文件匹配的浏览器，再执行包装脚本；包装脚本会生成内存测试凭据、启动真实 Uvicorn 与 Vite 同源代理，并在结束时停止服务和删除临时数据库：

```bash
cd web && ./node_modules/.bin/playwright install chromium && cd ..
python3 scripts/e2e.py
```

只核对测试发现、临时迁移和服务编排而不启动浏览器时，可运行 `python3 scripts/e2e.py --list`。浏览器报告只包含用例名、状态、耗时和源码位置；不保存截图、trace、视频、Cookie、请求正文、服务日志、数据库或凭据。CI 使用相同步骤；测试源码或 `--list` 成功不等于真实浏览器验收通过。

旧基线的执行记录见 `docs/evidence/bootstrap-2026-09-23.md` 与 `docs/evidence/foundation-report.md`；本机结果见 `docs/evidence/T010-windows-2026-09-28.md`。不要把启动说明当成已执行证据。未实现路径明确返回 501，未知路径 404，字段无效 422；正式运行不注入 Fake Runner。
