# EdgeVision — 边缘视觉模型管理与部署平台

EdgeVision 当前以目标检测为首个可验证场景，面向轻量单机环境串起数据、训练、模型、ONNX 验证与部署生命周期；ONNX 是部署主线，RKNN 仅保留未验证的扩展边界，不冒充实机能力。本仓库已交付范围/存储/接口基线、API 与 Worker 骨架以及迁移/测试基础。T020 真实身份、管理员账号管理与项目闭环已通过独立审查及 Linux CI 真实浏览器验收；T030 受限数据集上传、版本记录与纯校验核心已通过独立审查和 Linux CI 三项真实浏览器回归；T040 真实异步校验、任务日志/取消/恢复和报告下载已通过 Linux/Windows 进程及 Linux 浏览器 CI，具体范围与未执行项见 `docs/evidence/T040-cross-platform-acceptance-2026-11-04.md`；训练、模型和部署仍明确未实现。状态见 `docs/status.md` 与 `docs/evidence/T020-browser-acceptance-2026-11-04.md`。

## 许可

有权授权的项目原创源码与文档采用 **[AGPL-3.0-only](LICENSE)**。适用范围及排除项见
[LICENSE_SCOPE.md](LICENSE_SCOPE.md)，依赖与计划中的 ML 组件见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。第三方组件保留原许可；历史参考 ZIP、
数据集与权重不因本项目 LICENSE 自动获得授权。后续改动许可证不能单方面撤销既有 AGPL
副本权限。许可选择不代表训练资产或生产分发已经完成核验。

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

如已有旧版 `0001` 数据库，**先停 API/Worker、做一致性备份，并在副本上验证 `0001`→`0002_foundation`→`0003_worker`**；不要对唯一数据副本直接试迁移。全新开发目录才直接运行下面的迁移命令。

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

Worker 遇到不明遗留 running/cancelling 任务会停止领取并返回 4，不会静默重训。T040 使用独立 guardian、Linux subreaper/pidfd 或 Windows Job Object 回收整树。Windows 缺 receipt 时的主机重启安全阻塞，不能凭旧 PID 手工强制解锁。详见 ADR 0009 与 T040 报告。

检查/契约生成（把 `python3 scripts/dev.py` 换为 Windows 的 `py -3 scripts\dev.py`）：

```bash
python3 scripts/dev.py contract-generate
python3 scripts/dev.py contract-check
python3 scripts/dev.py check
```

`contract-generate` 从 FastAPI OpenAPI 生成 TS；`contract-check` 不修改跟踪产物。`check` 包括纯契约/脚本测试、后端 pytest、前端构建和契约漂移检查。兼容的 Bash 入口仍可使用 `bash scripts/dev.sh <命令>`。Windows 本机的运行结果见 `docs/evidence/T010-windows-2026-09-28.md`；此前 Linux 容器缺依赖的结论只适用于当时环境。

T020 身份/项目、T030 上传/pending 版本与 T040 上传→校验→ready/invalid 的真实浏览器回归使用锁定的 Playwright/Chromium，并且只连接测试入口创建的临时迁移数据库。先安装项目依赖和与锁文件匹配的浏览器，再执行包装脚本；包装脚本会生成内存测试凭据、启动真实 Uvicorn、Worker 与 Vite 同源代理；结束时停止服务，确认 guardian 回收后才删除临时数据库，无法确认时退出失败并保留隔离运行目录：

```bash
cd web && ./node_modules/.bin/playwright install chromium && cd ..
python3 scripts/e2e.py
```

只核对测试发现、临时迁移和服务编排而不启动浏览器时，可运行 `python3 scripts/e2e.py --list`。浏览器报告只包含用例名、状态、耗时和源码位置；不保存截图、trace、视频、Cookie、请求正文、服务日志、数据库或凭据。CI 使用相同步骤；测试源码或 `--list` 成功不等于真实浏览器验收通过。

旧基线的执行记录见 `docs/evidence/bootstrap-2026-09-23.md` 与 `docs/evidence/foundation-report.md`；本机结果见 `docs/evidence/T010-windows-2026-09-28.md`。不要把启动说明当成已执行证据。未实现路径明确返回 501，未知路径 404，字段无效 422；正式运行不注入 Fake Runner。


数据集操作：登录并创建项目→选择所属项目→上传受控 YOLO ZIP→点击“开始校验”。Worker 未启动时任务会真实停留 queued；执行时显示日志，无虚构进度。ready 可预览/下载报告，invalid 可下载错误报告；取消或主机执行失败恢复 pending，重新校验创建新 Job。归档项目禁止新任务，但已有任务仍可查看/取消。任务面板支持历史分页和终态最终日志读取。

T040 轻量进程测试：`cd backend && .venv/bin/python -m pytest tests/test_worker_process.py tests/test_worker_api.py`（Windows 用 `.venv/Scripts/python.exe`）；实际 HTTP 服务重启探针为 `tests/http_restart_probe.py`，只使用隔离夹具，不读取已有用户库。Windows CI 使用标准 windows-2022 runner 执行真实 Job Object 场景，精确通过版本与结果见 T040 跨平台验收；不覆盖未执行的整机重启和硬件故障。所有测试均无模型下载或训练。

## 可选 Linux CPU 训练（T050）

默认轻量 API 环境不安装 Torch。经过锁定的训练组合为 Linux x86_64 / Python 3.12、
Ultralytics 8.4.202、Torch 2.15.0+cpu、torchvision 0.29.2+cpu；CUDA 和 Windows ML 未验证。

1. 使用 Python 3.12 执行 `python scripts/install_ml.py`，创建独立 `backend/.venv-ml`，不会覆盖 `.venv`。
2. 显式获取固定官方资产：`python scripts/fetch_training_asset.py --output /your/private/yolo11n.pt`。
   仅允许固定 URL/size/SHA；资产不进入 Git。许可与来源见 THIRD_PARTY_NOTICES.md，项目许可不覆盖第三方资产。
3. 设置同一个 `PLATFORM_DATA_ROOT`，进入 backend，使用 `.venv-ml/bin/python -m alembic upgrade head` 迁移。
4. 停止 Worker，执行 `.venv-ml/bin/python -m app.training_probe --asset /your/private/yolo11n.pt`。
   探针持有全局锁并核对先前执行已退出；失败/过期探针不开放训练。不要手工编造能力记录。
5. API 和 Worker 都使用此联合解释器：`.venv-ml/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
   与另一个终端中的 `.venv-ml/bin/python -m app.worker`。Web 仍使用已有 npm/Vite 启动方式。
6. 上传并校验数据集至 ready，选择项目中的训练表单。只放行 YOLO11n、CPU、epochs 1–100、
   batch 1–16、320/640、固定 SGD 与受限初始学习率。重试创建新任务，不恢复旧任务。

每个任务在 GO 后才加载 ML；使用独立数据副本、禁用集成与下载、固定安全 checkpoint 类名单，
所有读取强制 weights_only。进程内 Python 审计不是 OS 网络沙箱。框架自动改 batch、非有限权重、
隐式修复/过滤数据和不完整 PT 均拒绝。完整 best/last 与最终真实指标同时满足证据要求才可成功。
模型下载移除本机路径等不必要 checkpoint 元数据，HTTP 不公开存储路径。

输入越大训练越慢；单次任务最多运行一小时并等待受管整树退出。空间预检为数据副本加 512 MiB
保留量，不是磁盘配额；存储失败不会发布部分模型。ready 数据不会因训练失败变为 invalid。
代码/环境/资产变化后需要重跑操作员探针。未确认退出的探针或 Worker 会阻止继续领取，需要先核对原执行，
不能删除记录或凭 PID 杀未知进程来绕过检查。当前验收仍见 docs/status.md。
