# T000 仓库、环境与启动包核验记录

时间：2026-09-23 UTC。目标仓库：`/workspace/scratch/be544824c543`；初始分支 `main`，基线 `57920e6`，无配置远端。开始前 `git status --short` 仅显示本轮上传的 `upload/` 未跟踪；未覆盖该文件。此目录是上轮同一毕设骨架，不是本次解压的规范包，也不是其他 KWin 项目。

## 启动包与现有资产

- 上传 `upload/edgevision-foundation(1).zip` SHA-256 `da1568e9b63239916ff3a3fc7e83942f291493c960a635d495f0a9be105ee0dc`。隔离提取在忽略的 `.audit/foundation-pkg-4043/`；`sha256sum -c SHA256SUMS` 全部 OK，退出 0。先读 START-HERE、prompt 01，再读项目 AGENTS/Git、包内 status/scope/architecture/contracts/environment/T000/T010/acceptance。
- 已读当前 `backend/app/main.py`、`worker.py`、数据库迁移、测试、`web/src/App.vue`、`web/src/api.ts`、依赖与路由配置、`contracts/api.ts`，以及四个现有 Skill。已有 Vue3/npm 工程可构建、页面依赖真实健康接口代码；原 Next.js 演示包留在 `reference/`，其硬编码业务数据不能使用。
- 同名规范没有直接拷贝覆盖。AGENTS/范围/架构/环境/验收/状态以当前合理内容为基础合并；新 contracts、任务卡和 Skill references/metadata 才按完整 SHA 校验后新增。四个同名 Skill 是**本项目仓库的同名流程**，保留原来的明确触发/输入/输出/停止段落并引入新包的边界和参考文件。Git 历史保留旧 T0–T9 草案，工作区内迁至 `docs/tasks/legacy-tasks.md`；当前入口为 T000–T070。
- 差异及取舍：旧 SSE → 启动包轮询；任务恢复旧 failed/INTERRUPTED → 新独立 interrupted 且须核实进程；手写全量 TS → Pydantic/OpenAPI 生成入口；包默认 pnpm → 沿用已可构建的 npm/Vite；旧 `0001` 不改，追加 `0002`。见 ADR 0005。旧管理页面原型既不运行也不变造能力。

## 环境、工具、来源

| 步骤 | 观察/退出码 | 限制 |
| --- | --- | --- |
| `git status --short --branch`、`git remote -v`、`git log -1` | 退出 0；main/57920e6；无远端，仅上传 ZIP 未跟踪 | 无外部仓库与 CI 权限信息 |
| `uname -srm`、`cat /etc/os-release`、`free -h`、`df -h` | 退出 0；Ubuntu 24.04.3、9 CPU、15 GiB RAM、约 30 GiB 可用 | 是本执行容器，不是用户机器 |
| `python3 --version`、`uv --version`、`node --version`、`npm --version`、`pnpm --version` | 均退出 0；3.12.14、0.12.17、24.19.0、11.9.0、11.19.0 | 未证明各库兼容 |
| `importlib.util.find_spec`（系统与 backend/.venv） | fastapi/sqlalchemy/alembic/pytest/httpx/uvicorn/torch/ultralytics/onnx/onnxruntime 均不可导入；系统 Pydantic 2.13.5 | 不等于用户机器缺依赖 |
| `uv sync --offline --extra dev` | 退出 1，缓存没有 FastAPI，提示网络禁用 | 没有安装系统包；轻量 Python API/迁移测试受阻 |
| GPU/设备只读探测 | 无 `nvidia-smi` 命令；无可信本地数据/权重或 RKNN 板卡证据 | GPU 是否存在和可用、PT/ONNX/RKNN 均 NOT_RUN |
| Agent 文件/终端/Git | AGENTS/四个 Skill 实际读入、文件/差异/终端命令均成功 | 本宿主手动读流程，未验证四个仓库 Skill 自动触发 |
| 官方资料检索 | FastAPI OpenAPI 与 Alembic SQLite batch 文档查询成功 | 只证明资料工具可用；版本适配需真实安装 |
| Chrome/CDP | 工具连接与文档读取成功；前次本机地址遇 ERR_BLOCKED_BY_CLIENT | 当前本地页面视觉/键盘操作仍 NOT_RUN；DeepSeek/GPT5.6 宿主未核验 |

用户已提供其个人电脑的 `uv sync`、旧版 `alembic upgrade head`、Uvicorn 启动日志；缺少新版提交、版本和迁移输出，不能用于本轮 A01/A02。学校正式题名/硬性 NPU 要求、目标机资源和可信数据/权重均待用户在对应阶段核验；它们不阻止当前容器内的纯契约和前端检查。

T000 结论：盘点与包合并已执行，本宿主轻量后端依赖缺失已明确。可进入 T010 的静态、前端与纯 Pydantic 部分；M0 的 ML 链路探测未通过/未执行，不能写 M0 全面通过。T010 新增证据归入 `foundation-report.md`。
