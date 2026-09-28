# 项目状态 · review_required（更新至 2026-09-28 UTC）

目标仓库本地 main，接入前基线 57920e6；上传 ZIP 仍在 upload/ 且未纳入项目提交。当前范围仅 T000/T010，结果送独立审查；T020 **blocked**，未开始。详细实际执行结果见 docs/evidence/foundation-report.md。M0 的盘点完成但 ML_CHECK_PENDING；M1 的 A01–A04 尚未全部通过，不能宣称地基验收通过。

2026-09-28 新增 Linux/Windows 项目级依赖安装与统一开发入口，见 README、ADR 0006 与 `docs/evidence/portable-bootstrap-2026-09-28.md`。本容器 Linux 预检、离线脚本/Worker 负向测试与前端构建通过；**真正依赖安装、本版本迁移、API HTTP 与 Windows 实机均未执行**，A01–A04 与 T020 状态不变。下表记录 2026-09-23 地基阶段已有资产及当时证据，不能以新增脚本覆盖其待补项。

| 模块 | 源码存在 | 本轮实际构建/运行 | 真实业务后端接入 | 验收 |
| --- | --- | --- | --- | --- |
| 旧 Next.js 原型 reference/ | 是，原件不改 | 本轮未重试；历史离线安装失败 | 否，仍有硬编码和计时成功 | 不可作为正式产品 |
| Vue3/npm/Vite 工作台 web/ | 是，保留原视觉并新增阶段路由 | npm 安装、类型检查/Vite 构建退出 0；隔离 HTTP / 和 /training 均 200 | 仅健康接口请求代码；本轮未连接实际 FastAPI | 浏览器截图/真实 API 交互 NOT_RUN |
| FastAPI 接口与 Pydantic DTO | 是，明示 501/422/404 规则 | 5 项纯契约测试通过、Python 语法编译退出 0；当前容器缺 FastAPI，HTTP 未启动 | 业务均占位 501（运行时未测） | A01、A04 NOT_RUN |
| Alembic 0001 + 新 0002 / SQLAlchemy Models | 是，0001 原样；0002 候选 | 语法检查通过；实际迁移/pytest 未运行 | 无 | A02 NOT_RUN，旧库不可直接升级 |
| Worker/状态协议 | 是，单实例和子进程占位 | 隔离最小测试表：一个 UNSUPPORTED_JOB 失败、第二个 queued；遗留 running 时退出 4 且不改状态 | 没有训练/导出 runner | 仅失败闭环烟测，进程恢复 T040 |
| OpenAPI/前端生成类型 | 生成脚本及本地 CLI 已有；生成产物无 | contract-generate 退出 2（缺 FastAPI） | 旧健康 TS 为明确临时桥接 | A03 未通过、生成与漂移检查待补 |
| 项目 4 Skill/AGENTS | 已逐项合并；保留明确触发/输入/输出/停止与参考文件 | 静态路径/格式检查通过；本宿主为手动读流程 | 不适用 | 自动发现/其他宿主未验收 |
| Ultralytics/PT/ONNX/RKNN | 无正式适配器与真实资产 | 未执行训练、模型导出、推理或硬件实验 | 无 | 全部未验收 |

## 技术与任务基线

单机双角色，Vue3/TS/Element Plus + FastAPI/Pydantic/SQLAlchemy/Alembic/SQLite，本地文件，独立 Worker/每任务子进程/单重任务槽，轮询日志；ONNX 部署主线、PT 与 ONNX 单图推理分别实跑、RKNN 扩展边界。新启动包 docs/contracts.md 规定公共语义，候选精确 Schema 为 backend/app/schemas.py；ADR 0005 记录与先前 SSE/状态/URL 的差异。旧 T0–T9 草案在 docs/tasks/legacy-tasks.md，现行任务为 docs/tasks/T000–T070。

## 待审查与领取闸门

1. 在有可信 Python 包源的开发环境锁定 uv.lock，并仅对**临时空库和原 0001 数据库副本**运行两次 Alembic 升级、检查外键/约束、执行 pytest；本轮没有执行，不能以用户旧版启动日志抵充。
2. 运行 contract-generate + contract-check，审查 OpenAPI，提交生成 TS 后用生成类型替换现有健康接口的临时手写桥接；当前无生成产物。
3. 同时运行新版 API 与前端，在能访问 localhost 的浏览器检查空态、路由、断线、键盘与窄屏；本轮仅通过构建与同进程 HTTP 200。
4. 核查学校是否把 NPU/边缘实机作为正式硬性要求、目标机器容量与可信数据/权重许可。无授权不下载模型或开始训练。

T000/T010 代码与文档交付状态为 review_required，A01–A04 没有满足完整通过条件；在审查与补证前 T020 仍 blocked。审查后另行放行，勿自动进入身份/项目业务开发。
