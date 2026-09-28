# YOLO 目标检测训练与部署辅助平台（架构骨架）

本仓库只交付范围基线、项目规则、接口/数据库/存储契约、API 与 Worker 骨架、迁移和测试基础。业务链路当前**未实现、未验收**。Windows T010 补证与审查状态见 `docs/status.md`、`docs/evidence/T010-windows-2026-09-28.md`；旧 Linux 证据保留在 `docs/evidence/foundation-report.md`。接手说明见 `docs/CODEX-HANDOFF.md`。

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

## 启动骨架

如已有旧版 `0001` 数据库，**先停 API/Worker、做一致性备份，并在副本上验证 `0002_foundation`**；不要对唯一数据副本直接试迁移。全新开发目录才直接运行下面的迁移命令。

Linux：

```bash
python3 scripts/dev.py migrate
python3 scripts/dev.py api
# 另开终端：python3 scripts/dev.py worker
# 再开终端：python3 scripts/dev.py web
```

Windows PowerShell：

```powershell
py -3 scripts\dev.py migrate
py -3 scripts\dev.py api
# 另开终端：py -3 scripts\dev.py worker
# 再开终端：py -3 scripts\dev.py web
```

浏览器访问 `http://127.0.0.1:5173/`；API 直接地址为 `http://127.0.0.1:8000/api/v1/health/live`，根路径 `/` 返回 404 是当前路由约定。前端默认从同源 `/api/v1` 访问服务，由 Vite 代理至 127.0.0.1:8000；部署时刷新 `/training` 等路由需要 SPA fallback。端口占用时可在启动命令前设置 `EDGEVISION_DEV_API_PORT` 和 `EDGEVISION_DEV_WEB_PORT`（例如 PowerShell 中 `$env:EDGEVISION_DEV_API_PORT='18000'; $env:EDGEVISION_DEV_WEB_PORT='15173'`），API 和 Vite 代理使用前者，Web 使用后者。Worker 遇到不明遗留 running/cancelling 任务会停止领取并返回 4，不会静默重训。Windows 已验证占位 Worker 的单实例、失败和遗留停领路径；真实任务的进程树清理与重启验证仍属 T040。

检查/契约生成（把 `python3 scripts/dev.py` 换为 Windows 的 `py -3 scripts\dev.py`）：

```bash
python3 scripts/dev.py contract-generate
python3 scripts/dev.py contract-check
python3 scripts/dev.py check
```

`contract-generate` 从 FastAPI OpenAPI 生成 TS；`contract-check` 不修改跟踪产物。`check` 包括纯契约/脚本测试、后端 pytest、前端构建和契约漂移检查。兼容的 Bash 入口仍可使用 `bash scripts/dev.sh <命令>`。Windows 本机的运行结果见 `docs/evidence/T010-windows-2026-09-28.md`；此前 Linux 容器缺依赖的结论只适用于当时环境。

旧基线的执行记录见 `docs/evidence/bootstrap-2026-09-23.md` 与 `docs/evidence/foundation-report.md`；本机结果见 `docs/evidence/T010-windows-2026-09-28.md`。不要把启动说明当成已执行证据。未实现路径明确返回 501，未知路径 404，字段无效 422；正式运行不注入 Fake Runner。
