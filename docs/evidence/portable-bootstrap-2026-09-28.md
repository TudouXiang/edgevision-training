# Linux / Windows 开发入口补充记录（2026-09-28 UTC）

任务范围：用户要求在 README 加入安装依赖脚本以支持 Linux/Windows；属于 T010 骨架入口补充，不放行 T020。起点本地 Git `main` 提交 `d5eade0`，`git status --short --branch` 只有 `## main`、无已有未提交修改；无远端。参照 AGENTS、arch-spec、architecture、status、T010。没有修改前端源码、包管理器或数据库迁移。

## 源码与决定

- `scripts/install_deps.py`：检查 Python/Node/uv/npm 与 npm 锁文件；`--check` 无安装；真实执行时按顺序 `uv sync --extra dev`（固定本地 `.venv`、不下载 Python；存在 uv.lock 时要求 locked）、`npm ci`（现有 package-lock）；单侧选择和失败即停。没有 Torch/Ultralytics/ONNX/RKNN 安装动作。
- `scripts/dev.py`：使用项目虚拟环境的 Python 来迁移、运行 API/Worker、生成契约/测试；npm 启动 Web。保留 `scripts/dev.sh` 包装。类型生成经 Node 运行本地 `openapi-typescript/bin/cli.js`，不依赖 POSIX npm shim。
- Worker 保留 T010 的 501/UNSUPPORTED_JOB 实情；针对当前单子进程添加 Windows 文件锁和直接终止路径、遗留任务停领；Windows boot 身份明确为未核实，真实进程树/重启仍归 T040。决策及回退见 ADR 0006。

## 当前 Linux 容器实际命令

| 命令 | 退出码、实际输出 | 能证明 / 不能证明 |
| --- | --- | --- |
| `python3 scripts/install_deps.py --check` | 0；列出 backend uv sync 与 web npm ci，`installation NOT_RUN` | 前置程序在本机可执行；没有安装任何项目包 |
| `python3 scripts/dev.py doctor` / `bash scripts/dev.sh doctor` | 0；Python 3.12.14、uv 0.12.18、Node 24.19.0、npm 11.9.0；最终项目虚拟环境中 Pydantic/FastAPI/pytest 均缺失 | 本机工具与旧 Bash 包装正常；后端依赖仍缺 |
| `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_contracts_unit.py' -v` | 0；5 项通过 | 纯 Pydantic 基础约束，非 HTTP/迁移验收 |
| `PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_dev_scripts_unit.py' -v` | 0；7 项通过，含安装失败即停、单实例锁、临时最小 SQLite 上的 UNSUPPORTED_JOB/遗留停领 | Linux 脚本及 Worker 负向烟测；临时手工表不等于 Alembic 迁移；Windows 进程未实跑 |
| `python3 -m compileall -q scripts backend/app backend/tests`；`bash -n scripts/dev.sh` | 各 0 | 语法可用，不能证明 Windows 执行 |
| `cd web && npm run build` | 0；vue-tsc + Vite 7.3.6，3477 模块转换 | 既有 Vue 前端在 Linux 构建；未运行 Windows 构建或真实 API |
| `python3 scripts/dev.py check` | 1；最终入口使用项目 `.venv`，第一组单元测试即缺 Pydantic；纯测试的 5+7 通过结果来自上面单独运行的系统 Python 命令 | 整体检查未通过；后续 pytest、前端构建/契约步骤未由该命令执行 |
| `python3 scripts/dev.py contract-generate` | 2；`Missing project-local Python dependency: fastapi` | 本轮没有生成 OpenAPI/TS，A03 不通过 |

一次早期入口试运行 `uv run --no-sync` 在此容器因解释器/旧环境不一致重建了被忽略的 `backend/.venv`；当时 `dev.py check` 的 5+6 纯测试通过后因缺 pytest 退出 2。最终 `dev.py` 改为直接调用项目虚拟环境解释器，并在该环境中运行基础测试。当前 `.venv` 仍无 Pydantic/FastAPI/pytest；未动用户数据库或跟踪文件。`npm run build` 使用此前已有 `web/node_modules`，本轮没有运行 `npm ci`；安装脚本的真实下载/安装 **未执行**。Linux Alembic 迁移、API HTTP、浏览器交互、训练和硬件验证 **未执行**。Windows 的安装、PowerShell 命令、Alembic、FastAPI、Web、Worker 锁/进程与浏览器 **全部未执行**；离线单测中的 `.cmd` 路径只是模拟参数，不是 Windows 运行证据。

后续补证：目标 Linux 与 Windows 机器分别运行 README 的 `--check`、真实安装、临时空库及旧库副本的迁移、`contract-generate`/`contract-check`、`check`、API/Web/Worker 的真机交互；Windows 的真实任务进程树取消/重启待 T040。此报告状态 `review_required`，T020 仍 `blocked`。
