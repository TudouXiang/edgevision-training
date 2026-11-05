# T030 数据导入与校验核心交付记录

> 当前更新：T030 已由独立审查与精确提交的真实 Chromium CI 验收；见 [2026-11-04 验收记录](T030-browser-acceptance-2026-11-04.md)。下文保留候选阶段和失败修复的原始事实。

状态：`review_required`。日期：2026-11-04 UTC。实现基线为 `56c34f2ccc3d2dea46360c450079f373437f5e8f`；T030 首次候选已发布为分支 `feat/t030-dataset-core` 的 `29107984e7c6204072af08363662205fd24a496a`，本报告所述浏览器修复尚未提交。远端 main 外部合并 T020 到 `f6db48a68534a93a50110e09750243e39417df7f`，其树与实现基线相同；本实现未 merge/rebase。T020 前置已 accepted；T040 未放行、未实现。

## 范围与决定

本候选先以 ADR 0008 冻结受控 ZIP、YAML、图片与 YOLO label 规则，再实现以下单一纵向切片：

- 原始 ASGI multipart 流限流，单一 ZIP `.part` staging、SHA-256、flush/fsync、中央目录预检和原子 source 发布。
- 最终短写事务重新鉴权/检查归档；同名上传串行分配新 version/parent_id，不覆盖旧 snapshot；真实返回 pending。
- 无数据库/网络依赖的纯解压/校验服务，结构化相对 path/line 错误、确定性文件/快照摘要、类别/计数/warning 和有界样本/框预览。
- owner/admin 数据集列表、详情、ready-only 预览元数据与鉴权图片流；pending/invalid 不暴露预览。
- 前端项目选择、ZIP 上传、pending/版本列表分页、ready 的图片+框+类别 SVG 有限预览；切项目/退出/并发读写的迟到响应保护。
- `/datasets/{id}/check`、Job/Worker、训练输入绑定保持 501/未实现；没有把纯校验成功写成 ready，也没有在 HTTP 请求执行重型解压/图片 decode。

数据库复用 `0002_foundation`，没有修改历史迁移。新增轻量锁定依赖为 Pillow 12.3.0、python-multipart 0.0.33、PyYAML 6.0.3；未安装/导入 Torch、Ultralytics、ONNX 或 RKNN。测试 ZIP/图片均由测试代码在临时目录生成，不含用户数据、模型或外部数据集。

## 冻结的关键规则

- root `data.yaml` 或恰好一层 wrapper；小写 JPEG/PNG/TXT 固定目录；ZIP64/multidisk/SFX、链接/特殊文件、危险/碰撞路径、未知文件均拒绝。
- 512 MiB ZIP、128 KiB multipart 开销、32 MiB 中央目录、20,000 条目、2 GiB 解压、512 MiB 成员、200:1 大成员及聚合压缩比；图片 50 MiB/3,000 万像素。
- YAML 64 KiB、UTF-8、无 alias/anchor/tag/重复/未知键、32 层/10,000 节点；names 为列表或连续整数 mapping，nc 可省略但存在时须匹配。
- 每张图片必须有 label；缺失/孤立是错误，空 label 是显式背景 warning。标签 5 列、整数类 ID、有限坐标、正宽高、完整框不越界。
- 最多 100 个预览样本、每样本 200 个预览框；截断只影响显示，超出预览范围的全部输入仍会验证。

## 实际命令与结果

环境：Linux 6.18.57 x86_64，Python 3.12.14，Node 24.22.1，npm 11.9.0，uv 0.13.5。

1. 项目隔离依赖更新：
   - `UV_CACHE_DIR=/tmp/edgevision-uv-cache uv add --project backend 'python-multipart>=0.0.20,<1' 'pillow>=11,<13' 'pyyaml>=6,<7'`
   - 退出 0；解析 34 packages，安装上述 3 个包并更新 `backend/uv.lock`。
2. T030 定向后端：
   - `cd backend && .venv/bin/python -m pytest tests/test_dataset_api.py tests/test_dataset_validation.py -q`
   - 退出 0；`34 passed`，3.73s。覆盖正常 root/wrapper、names 两种表达、空/缺 label、非有限/越界/类别、坏图/像素、路径/链接/重复/特殊/压缩/中央目录限制，及 HTTP staging/权限/竞态/清理/版本/预览。
3. 前端定向：
   - `cd web && npm test -- --run && npm run build && npm run typecheck:e2e`
   - 退出 0；Vitest `6 passed`；Vue typecheck + Vite build 成功；Playwright TS typecheck 成功。
4. 完整聚合：
   - `backend/.venv/bin/python scripts/export_contract.py && backend/.venv/bin/python scripts/dev.py check`
   - 退出 0；先生成 OpenAPI/TS；unittest 6 + 9 通过；pytest `60 passed`（含 8 subtests），9.68s；Vitest `6 passed`；生产构建成功；重新生成契约无漂移。
5. 浏览器发现：
   - `backend/.venv/bin/python scripts/e2e.py --list --report-dir /tmp/edgevision-t030-e2e-list`
   - 退出 0；发现 3 个 Chromium 场景（T020 两项 + T030 一项），`completed=0`、`browser=NOT_RUN`。本宿主遵守既有浏览器限制，未尝试本地真实 Chromium；候选发布后须由 GitHub 托管 runner 实际执行。
6. 静态清洁：
   - `backend/.venv/bin/python -m py_compile backend/app/dataset_validation.py backend/app/dataset_storage.py backend/app/main.py backend/app/schemas.py backend/app/services.py`、`UV_CACHE_DIR=/tmp/edgevision-uv-cache uv lock --project backend --check`、`git diff --check`
   - 均退出 0；最终仍须由独立审查者在候选工作区重跑。

已观察的 warning 为既有 Starlette/httpx 与 Alembic 配置 deprecation，以及故意构造重复 ZIP 名称的测试 warning；没有测试失败或静默跳过。

## A06/A07 与负向证据

- A06 数据安全：**T030 核心范围 PASS / 完整异步链路 NOT_RUN**。纯服务与真实 HTTP staging 覆盖正常小 ZIP、路径逃逸/绝对/反斜杠/NUL/Windows 路径、链接/特殊文件、重复/大小写/文件目录碰撞、条目/中央目录/成员/总解压/压缩比、损坏 ZIP/CRC/图片、超像素、YAML 复杂度、坏 label/NaN/Inf/越界类和框。T040 Worker 的真实 queued→validating→ready/invalid、取消/恢复尚未执行。
- A07 不可变输入：**T030 Dataset 范围 PASS / 训练绑定 NOT_RUN**。同名串行及双线程并发上传产生 v1/v2 独立 ID，v2.parent_id 指向 v1；source 文件不覆盖，碰撞/DB 失败只清理本次目录。训练 Job 绑定和基础权重属于 T050，未执行。
- 权限/竞态：owner/admin 正向与跨 owner 404；缺 CSRF 403；归档 409；在 staging 期间归档、禁用用户或撤销 session，最终事务分别拒绝且不留 Dataset/source。fsync 失败返回规范化 503 并清理 `.part`；发布后 DB 失败保留既有目录且清理本次目录。
- 未校验数据：HTTP 成功固定为 pending，counts=null、classes=[]，无 snapshot；preview 返回 409，check 在带 Idempotency-Key/授权后仍为 501。测试中 ready 记录只由隔离测试调用纯 validator 后显式构造，用于验证 DTO/授权/图片流，生产路径没有测试后门。

## 文件与契约影响

- 核心：`backend/app/dataset_storage.py`、`dataset_validation.py`、`config.py`、`main.py`、`schemas.py`、`services.py`。
- 依赖/契约：`backend/pyproject.toml`、`backend/uv.lock`、`contracts/openapi.json`、`contracts/generated/openapi.ts`。
- 前端/浏览器：`web/src/{api.ts,App.vue,style.css,App.test.ts}`、`web/e2e/t030.e2e.ts`、`scripts/e2e.py`、CI workflow。
- 测试：`backend/tests/test_dataset_api.py`、`test_dataset_validation.py` 及 T020 回归期望更新。
- 设计/说明：ADR 0008、api/contracts/storage/status/task 与本报告。

公共差异：API 版本 0.3.0；dataset list/upload/detail 从占位变为真实实现；samples 从错误的 `Page[ArtifactPublic]` 改为 `Page[DatasetSamplePublic]`，新增 owner-aware sample image 路由；capabilities.datasets 表示 staging/list/preview 核心可用，不表示异步校验或训练可用。

## 首次托管浏览器运行与修复

- GitHub Actions run `41785821044` 的聚合后端、前端单元测试、生产构建及新增 T030 浏览器场景通过；既有 T020 两个浏览器场景分别在 `web/e2e/t020.e2e.ts:98` 与 `:228` 失败。失败证据保留在该 run 及下载的安全 artifact；没有把首次失败运行改写为成功。
- 原因是 T030 新增“所属项目”下拉框后，项目名称同时出现在项目卡片与 `<option>`，旧的页面级 `getByText(name, { exact: true })` 因 strict locator 匹配两个元素而失败，并非项目功能或数据错误。
- 修复只把正向名称断言限定到对应 `article.row-card`，保留原有“项目卡真实可见”的检查；跨 owner 的页面级零匹配断言仍保持，未弱化权限检查。其他项目名称正向断言同步限定到项目卡，避免同类歧义。
- 375px 下拉框补充 `width/max-width/min-width` 与省略显示约束，防止 160 字符项目名凭 intrinsic width 撑宽面板；项目卡仍完整换行展示名称，浏览器用例继续检查页面无水平溢出。
- 本修复需新的托管 Chromium run 才能接受；`41785821044` 仅作为“首次运行失败并定位原因”的负向证据。

## 未执行与后续闸门

- 真实 Linux Chromium：首次候选已由 GitHub Actions run `41785821044` 执行；T030 新场景通过，但两个既有 T020 场景因 locator 歧义失败，因此整体仍未接受。当前修复必须由新的托管 run 重跑三项场景，不能把该失败 run 当作通过证据。
- Windows、实际 TLS、磁盘耗尽/进程崩溃/多进程压力、Worker 取消恢复：未执行。
- 用户真实数据、大模型、训练、PT/ONNX/RKNN/NPU：未使用、未执行。
- T040 只有在本候选独立代码/安全审查和真实 CI 浏览器证据通过后才能领取；届时复用纯 validator，写 report，原子发布 snapshot/ready 或 invalid，不能把 HTTP 请求改成长任务。
