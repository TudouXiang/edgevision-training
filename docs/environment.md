# 现有资产和工具核验（2026-09-23 UTC）

> 本文记录 2026-09-23 至 09-28 的旧 Linux 工作区观察，不能当作 2026-09-28 Windows 接手时的当前状态。本机事实、Git 新历史及执行证据见 `docs/CODEX-HANDOFF.md` 与 `docs/evidence/T010-windows-2026-09-28.md`。

## 来源盘点

当前工作目录启动时只有 `.codex/` 占位；`rg --files` 无业务文件，`git status` 报 `not a git repository`。没有可读的仓库、项目配置或已提交前端。本轮初始化了新的本地 Git 仓库，未有远端。另一本地工作区存在 `edgevision-studio-frontend.zip`，原始 SHA-256 为 `c6f5bb8f8fc561e52caf69f32439c2d0505801f2f85d33191657987d4a964f41`，已复制到 `reference/`，没有修改原文件。另有较早的前端需求文本和示例图片；本轮最新范围优先。没有收到独立的「附带基线」文件，冻结依据是本轮用户指令与先前 2026-09-22 确认的设计约束。

原前端为 Next.js 16 / React 19 / Vinext + Cloudflare 的 Sites 原型；有源码和锁文件。`app/api/overview/route.ts` 返回写死统计；`app/platform-app.tsx` 有计时器推进训练 epoch/转换进度、硬编码日志及 Redis/Celery 信息、客户端角色切换。其源码**存在**，但不满足真实接入。离线 `npm ci --offline --ignore-scripts --no-audit --no-fund` 缺少缓存包，退出码 1；因此本环境**尚不能证明可构建**，不能推断项目本身构建失败。真实后端已接入：否；业务验收：否。

## 工具与依赖

| 项目 | 实际检查 | 结论 |
| --- | --- | --- |
| 文件 | `rg --files`、`ls`、ZIP 清单与源码内容 | 可读写；工作目录初始无业务源码 |
| 终端 | 执行 Python、Node、Git 和解压检查 | 可用 |
| Git | `git --version`、`git status`、`git init` | 2.51.1；新仓库无远端 |
| 文档查询 | 官方 FastAPI/Alembic/Ultralytics/SQLite/ORT 页面搜索 | 可用，架构参考到文档链接 |
| 浏览器 | 浏览器运行时成功连接 Chrome/CDP 并读到 API 文档 | 工具可用；本地应用页面尚未在浏览器验收 |
| 环境 | Python 3.12.14、Node 24.19.0、npm 11.9.0 | 满足骨架解释器前置条件 |
| Python 包 | importlib 检查 | pydantic 有；FastAPI、Uvicorn、SQLAlchemy、Alembic、pytest、Ultralytics、ORT 暂无 |
| npm 缓存 | 原型离线安装 | 缺依赖；未自动安装系统组件 |

命令、退出码、实际服务和迁移结果见 `evidence/bootstrap-2026-09-23.md`；尚未运行的训练/GPU/NPU 测试须标记未执行。

## T000 当前仓库复核（本次启动包接入，2026-09-23 UTC）

以上“初始工作区为空”是上一轮的**历史观察**。本次当前仓库为 `/workspace/scratch/be544824c543`，Git `main` 基线 `57920e6`、没有远端；开始编辑前仅 `upload/edgevision-foundation(1).zip` 未跟踪，未修改上传原件。该包 SHA-256 `da1568e9b63239916ff3a3fc7e83942f291493c960a635d495f0a9be105ee0dc`，其 SHA256SUMS 逐项通过。用户个人机器提供了旧版 `uv sync`、`alembic upgrade head`、Uvicorn 启动日志，但那不是本容器本轮 `0002` 迁移证据。

| 当前项 | 实测/证据 | 结论 |
| --- | --- | --- |
| 系统资源 | Ubuntu 24.04.3、Linux 6.18.44 x86_64、9 CPU、15 GiB RAM、约 30 GiB 空间 | 仅此容器，不能当作用户开发机容量 |
| 语言/包管理 | Python 3.12.14、uv 0.12.17、Node 24.19.0、npm 11.9.0、pnpm 11.19.0 | 已有 npm lock 与 Vue 构建可复用，不改换包管理器 |
| 后端 Python 包 | `importlib.util.find_spec`：仅 Pydantic 可见，FastAPI/Uvicorn/SQLAlchemy/Alembic/pytest/httpx/Ultralytics/ONNX/ORT/Torch 缺失 | API/迁移/pytest/模型链路本容器不可运行 |
| 离线获取 | `cd backend && uv sync --offline --extra dev` 退出 1，FastAPI 包不在缓存 | 没有全局/系统安装；需要有包源的目标环境 |
| GPU/板卡 | 无 `nvidia-smi` 命令；无 RKNN 目标设备、可信数据/权重 | 存在性/可用性不能由文件缺失推断；训练/导出/实机全 NOT_RUN |
| Agent 文件/终端/Git | 读 AGENTS 和 4 个 Skill，实际 Git 状态/差异、文件写入及命令执行 | 本宿主可用；4 个项目 Skill 未自动暴露，已显式读取流程 |
| 文档查询/GitHub | 官方 FastAPI 与 Alembic 文档成功检索；GitHub 工具可发现但项目无远端，不调用写入 | 文档查询可用，远端/CI 未验证 |
| 浏览器 | 浏览器 Chrome/CDP 接口可连接；上轮对本机地址返回 ERR_BLOCKED_BY_CLIENT；本轮仅本机 HTTP 自检 | 云浏览器无法完成此工作区视觉验收；不标 A04 PASS |

目标机器上的可信样本/权重、学校正式题名和 NPU 是否硬性要求仍待核对。其他宿主（DeepSeek/GPT5.6）的 Skill 自动触发、测试及浏览器能力未执行，不以本宿主能力代替。详见 `evidence/T000-report.md` 与 `evidence/foundation-report.md`。

官方参考：[FastAPI OpenAPI](https://fastapi.tiangolo.com/how-to/extending-openapi/)、[Alembic SQLite batch 与外键](https://alembic.sqlalchemy.org/en/latest/batch.html)。文档页面可访问不证明目标环境依赖可用。

## 2026-09-28 跨平台开发入口补充

目标仓库基线 `d5eade0`、编辑前工作区干净。当前 Linux 容器 Python 3.12.14、uv 0.12.18、Node 24.19.0、npm 11.9.0；新增标准库安装脚本预检通过，但未实际安装依赖。当前 `backend/.venv` 缺 FastAPI 与 pytest，后端 HTTP/迁移/生成未验证。Windows 原生系统/PowerShell 不可用，路径与 Worker 兼容代码只完成静态及 Linux 上的占位进程测试，不能宣称 Windows 运行通过。详细命令、失败和补证方式在 `evidence/portable-bootstrap-2026-09-28.md`。
