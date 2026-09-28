# 骨架建立与工具核验证据

日期：2026-09-23 UTC。机器：当前隔离工作空间。原始命令/输出摘要及退出码如下；这里只列出实际执行的步骤。代码版本以本仓库最终本地提交为准。

| 对象 | 实际命令/动作 | 退出/结果 | 可据此证明 |
| --- | --- | --- | --- |
| 目录与 Git | `rg --files`、`git status --short --branch`（初始化前） | 无业务文件；Git 退出 128 `not a git repository` | 工作区无可覆盖的原仓库 |
| 历史前端 | `unzip -Z1 ...frontend.zip`，读取 package/API/页面源码，SHA-256 | SHA `c6f5bb8f8fc561e52caf69f32439c2d0505801f2f85d33191657987d4a964f41` | Next.js 原型源码存在且返回假概览/假进度 |
| 历史前端依赖 | `npm ci --offline --ignore-scripts --no-audit --no-fund` | 1，缺 `zod-validation-error-4.0.2.tgz` 缓存 | 不能证明该原型能在本环境离线构建 |
| 终端/运行环境 | `python3 --version`、`node --version`、`npm --version`、`git --version` | 3.12.14 / 24.19.0 / 11.9.0 / 2.51.1 | 解释器存在 |
| 资料与浏览器 | 官方 FastAPI/Alembic/SQLite/Ultralytics/ORT 文档检索；浏览器 Chrome/CDP 初始化及文档读取 | 两者成功；本地页面导航被浏览器报告 ERR_BLOCKED_BY_CLIENT | 工具可用，但当前浏览器不能验收本机页面 |
| 第三方 UI Skills | 逐文件核对 Git blob SHA；`quick_validate.py`；`search.py --design-system` 与 Vue 栈检索；安装后核对远端目录 | 47/47 UI Pro Max 文件相符；两个 Skill 有效、可读 | 指南来源可信，设计检索已执行 |
| 正式前端依赖 | `cd web && npm install --no-audit --no-fund` | 0，项目局部安装 | 前端包可获取 |
| 正式前端构建 | `cd web && npm run build` | 0，Vue TS 校验 + Vite v7.3.6 构建；最终 CSS 48.95 kB、JS 141.32 kB | 源码可构建；不证明业务功能已接通 |
| 正式前端服务 | 同一隔离进程内启动 Vite 并请求 `http://127.0.0.1:5173/` | HTTP 200，返回产品标题 | 最小页面服务可启动，不代表浏览器视觉通过 |
| Python 包 | `importlib.util.find_spec`、`uv sync --extra dev`、`pip download fastapi --index-url https://pypi.org/simple --no-deps --timeout 3 --retries 0` | FastAPI/SQLAlchemy/Alembic/pytest 缺失；uv 反复重试后人工中断 130；pip 退出 1 | 不能运行实际 FastAPI 或 Alembic |
| Python 语法 | `python3 -m compileall -q backend`（单独再次执行） | 静态语法检查无输出，退出 0 | Python 文件可编译，不证明迁移执行 |
| Worker 不伪成功 | `python3 -m app.worker --once`，输入为 `.audit/worker-fixture` 隔离最小测试表的两个 queued job | 0；首个 `failed/UNSUPPORTED_JOB`，事件 running→failed；第二个仍 queued；无成功结果 | 骨架队列拒绝未实现任务；此测试**不是正式 Alembic 迁移** |

未执行：真实 `alembic upgrade head`、FastAPI 请求、pytest、训练、ONNX 导出/推理、部署包、GPU/NPU/RKNN 硬件实验、浏览器实际截图/键盘审查。它们需要依赖可获取、真实输入或目标设备。
