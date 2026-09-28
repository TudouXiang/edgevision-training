# ADR 0006：Linux / Windows 项目级安装与开发入口

状态：T010 候选，待审查；2026-09-28。请求：在 README 增加依赖安装脚本，使当前骨架可在 Linux 与 Windows 使用。

## 当前事实与最小调整

原基线为 Vue/npm + FastAPI/uv/SQLite，`scripts/dev.sh` 仅限 Bash；Worker 直接导入 `fcntl`、读取 Linux `/proc`、发送 POSIX 进程组信号；前端类型生成调用 POSIX npm 可执行文件。没有 Windows 实机证据。新增标准库 `scripts/install_deps.py` 与 `scripts/dev.py`，保留旧 Bash 入口；仅让当前占位 Worker 使用对应平台文件锁与受控单子进程，类型生成通过 Node 调用已有包的本地 CLI。前端、公共 API、数据库结构和产品范围不变。

项目已有 npm 锁文件，继续用 `npm ci`；Python `uv.lock` 当前缺失，首次解析应审查生成物，后续同步要求 `--locked`。强制后端虚拟环境在 `backend/.venv`、禁止 uv 自动下载 Python；脚本不安装系统工具或 ML 包。运行入口直接调用 `backend/.venv` 的解释器，避免 `uv run --no-sync` 在本机解释器变化时重建虚拟环境。独立 OS 脚本会重复命令且容易漂移，改包管理器则涉及额外迁移，均不采纳。

## 失败、验证与回退

脚本缺前置、版本低、锁文件缺失或包源不可用时返回非零；安装前预检可使用 `--check`，不表示真正安装或服务通过。原有 Bash 命令保持兼容，回退可恢复旧入口和移除新脚本，无数据库迁移。`npm ci` 按 npm 语义重建 `web/node_modules`；用户已有库须先备份并在副本核验迁移。

Windows 当前只能对占位 `app.task_process` 单进程做直接终止；`host_boot_id` 记录为 `windows-unverified`，不能用于进程身份判定。Worker 重启遇到 running/cancelling 始终停领。T040 引入真实任务前必须设计并实测 Windows 进程树终止、取消竞争、遗留进程归属和 OS 重启。Linux 本轮可执行静态/脚本检查；Windows 安装、迁移、API、Worker、浏览器及硬件运行 **未执行**。状态与命令见 `docs/evidence/portable-bootstrap-2026-09-28.md`。

## 2026-09-28 Windows 接手补证

上述 `uv.lock` 缺失与 Windows 未执行描述是原 Linux 工作区在写此 ADR 时的事实。新 Windows 源码快照已包含 `backend/uv.lock`，并在本机完成项目环境预检、隔离迁移、API/Web、占位 Worker 和浏览器核验；实际重新安装依赖仍未执行。为避开已有服务，`scripts/dev.py` 与 Vite 增加可选的 `EDGEVISION_DEV_API_PORT`、`EDGEVISION_DEV_WEB_PORT`，默认端口不变。结果与限制见 `docs/evidence/T010-windows-2026-09-28.md`；真实任务的 Windows 进程树验证仍属 T040。
