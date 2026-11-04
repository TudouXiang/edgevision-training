# 当前状态 · T060 E 重建候选（2026-11-04 UTC）

T050 的既有验收保持原范围。未发布的旧 T060 工作区已丢失，本轮从公开 T050 `3b5b8ec785be595dd82a15fe94adcb7d102396f2` 重新实现，**不沿用旧候选测试结果**。

E（可信模型 ONNX 导出）的后端、严格契约、前端和验证脚本已形成源码检查点，独立静态审查已收口，新一轮轻量整合回归为后端 356 passed/9 skipped、前端 38 passed，构建/契约通过；详见 [重建记录](evidence/T060-rebuild-recovery-2026-11-04.md) 与 [后端范围](evidence/T060-export-rebuild-core.md)。隔离 CI 的静态方案审查已收口，但实际执行仍未发生。最终源码与命令范围见 [检查点记录](evidence/T060-rebuild-checkpoints.md)。源码已按阶段提交并另存持久备份，不等同于完整项目交付或业务验收。

**真实 ONNX/ORT、ML HTTP/浏览器、容器隔离、Windows 新增 E 行为均未执行，E 未 accepted。** 默认自动工作流暂不运行真实 ML；隔离方案须完成审查并获准后才能实际验证。I（真实图片推理）与 P（独立部署包）继续保持规范化 501，不越过 E 验收闸门。没有发布图片、模型权重或原始运行证据。

公开源码 `0455566` 已通过 [Linux/Windows 普通 CI](evidence/T060-source-ci-2026-11-04.md)，ML job 明确跳过。此结果不解除 E 原生验收闸门。

浏览器证据计数另有独立修正（静态复审与轻量整合回归已通过：371 后端/9 跳过、47 前端，增量远端 CI 待执行）：匿名 schema v2 区分执行、跳过、未运行与重试，不再把所有回调写成 completed；[验证记录](evidence/T060-browser-evidence-counts-2026-11-04.md)。仅报告器/离线回归和发现检查，不推进 E/I/P 验收。

以下保留历史阶段记录；遇到差异以本节为准。

---

# 当前状态 · T050 accepted / T060 前检（2026-11-04 UTC）

精确提交 `c398426b2ba9369d769479ca3fcb7c09600f7bab` 的三项 CI 全部通过：Linux 轻量回归、实际 CPU 训练与真实浏览器、Windows 既有进程回归。T050 在固定 Linux CPU 小规模闭环范围 accepted；完整范围和未执行项见 [T050 CI 验收](evidence/T050-ci-acceptance-2026-11-04.md)。T060 进入依赖/导出前检，尚未实现 ONNX/ORT、推理或独立部署。

以下保留分阶段记录；遇到状态差异以上述最新结论为准。

---

# 当前增量 · T050 review_required（2026-11-04 UTC）

固定 Linux CPU 训练闭环已实现：真实 HTTP/受管 Worker 单轮合成输入、真实轮次指标、净化且安全重载的 best/last、
完整束发布和鉴权下载均本地通过。未发布资产；CUDA、Windows ML、ONNX/RKNN 和正式精度实验不在此次实测范围。
具体 Job/Artifact/hash、失败历史、轻量及实际 ML 策略测试见 [T050 实现报告](evidence/T050-report.md)。
远端精确提交的 Linux/Windows 既有矩阵与新增训练浏览器 CI 仍待执行，不提前称 A11/A12 accepted。
现有 T040 accepted 基线保持；以下历史状态按原日期保留。

---

# 项目状态 · T040 accepted（2026-11-04 UTC）

T040 已完成独立审查及精确源码 `a61321ce3247c6e33c6c5462085da56f1e194b52` 的 Linux/Windows CI。Linux 105 项后端、10 项前端、4 场景真实 Chromium、构建/契约及真实 API 重启通过；Windows 4 项原生解释器探针、40 项进程/API/决策测试及真实 API 重启通过。证据与失败历史见 [跨平台验收](evidence/T040-cross-platform-acceptance-2026-11-04.md)。

**accepted 仅指已实测的受管进程与数据集异步闭环。** 整机重启/物理掉电、真实磁盘耗尽、用户旧库、实际 TLS、人工视觉、Windows 浏览器及 ML/硬件未实测，不泛称全部 A10 或完整平台已通过。Windows 无 receipt 时安全停领，不自动重跑。项目所有者已委托选择原创代码与文档的 AGPL-3.0-only 许可，边界见 [ADR 0010](adr/0010-project-licensing.md)。T050 已完成限定 Linux CPU 联合环境/官方权重/本地样本[前检](evidence/T050-preflight-2026-11-04.md)，按 [ADR 0011](adr/0011-t050-fixed-training-adapter.md) **ready for implementation（非 accepted）**。仓库训练仍未实现，A11/A12、Windows ML/CUDA 与发行未验收；COCO8 许可差异未解决，仅作私有本地技术烟测，不再分发。

新库目标 `0003_worker`。旧库须停 API/Worker、备份并在一致性副本验证后升级。缺整树退出证据时停止领取；取消/Worker 中断恢复 Dataset pending，内容错误才 invalid。完整协议见 [ADR 0009](adr/0009-t040-managed-worker.md)。

---

以下是 T040 开始前的已接受基线，保留历史日期与证据：

# 项目状态 · T030 accepted / T040 ready（2026-11-04 UTC）

T030 受限数据导入、不可变版本、纯校验核心、授权预览和前端已通过独立审查，以及提交 `a9309e7d9be279ca1143c1a49dd31d2fdfe085f5` 的 [GitHub Actions 41786393552](https://github.com/TudouXiang/edgevision-training/actions/runs/41786393552)：60 项后端、6 项前端、构建/契约和三项真实 Chromium 回归通过。**T030 accepted（Linux 核心范围）**，T040 **ready**。精确版本、失败修复与限制见 [T030 验收](evidence/T030-browser-acceptance-2026-11-04.md)。

生产上传仍固定为 pending，不能训练/预览；`/check` 仍 501。T040 将实现真实 Worker、日志、取消/恢复及 ready/invalid 发布。Windows 新功能、实际 TLS、人工视觉检查、真实 ML/ONNX/边缘硬件均未验收。远端 main 的外部 T020 合并为 `f6db48a68534a93a50110e09750243e39417df7f`，T030 发布在独立功能分支，未由本次操作合并 main。

## 历史 Windows T010 验收（2026-09-29）

Windows 本机已对项目级后端依赖同步/核对（26 个已安装包无需更改），并完成隔离空库重复迁移、代表性 `0001` 一致性副本升级、OpenAPI/TS 生成与漂移检查、真实 API/Worker/Web HTTP、浏览器窄屏/键盘/刷新/断线检查。修复独立审查发现的 `cancelling→failed` 守卫漏项后，原样 `bash scripts/dev.sh check` 退出 0：纯契约 6 项、脚本/Worker 9 项、pytest 20 passed、前端 build 和 contract-check 通过。A01–A04 **PASS**；独立 [`change-review`](evidence/T010-change-review-2026-09-29.md) 结论 `accept`，T010/M1 **accepted**，T020 **ready**。原始命令、退出码、数据/代码指纹和边界见 [`Windows 复核报告`](evidence/T010-review-2026-09-29.md)。`backend/uv.lock` 和生成契约已在本机 Git 基线。真实旧用户库迁移、ML/ONNX/RKNN、真任务进程树仍未执行。

## 历史 Linux 工作区记录

以下表格和命令结论属于 2026-09-23 至 09-28 的 Linux 隔离工作区，当时的 FastAPI/迁移/Windows 未执行结论仍保留作原始证据，当前本机结果以上述 Windows 报告为准。Linux 跨平台入口记录见 `docs/evidence/portable-bootstrap-2026-09-28.md`，地基报告见 `docs/evidence/foundation-report.md`。

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

1. T030 核心已验收。T040 先完成进程/发布协议 ADR，再实施真实子进程与 Linux/Windows 故障测试，不能沿用占位 Worker 冒充完成。
2. 真实旧用户 `0001` 库若将来提供，先停 API/Worker、备份并在一致性副本验证；本轮仅有代表性隔离样本。项目级后端同步没有重装已存在的 26 个包，已有环境的可运行性与全新环境可重装性分开判断。
3. T040 前分别在 Linux/Windows 验证真实任务进程树取消、重启和恢复；不得以占位 Worker 的路径替代。
4. 核查学校是否把 NPU/边缘实机作为正式硬性要求、目标机器容量与可信数据/权重许可。无授权不下载模型或开始训练。

T000 的历史盘点仍标 `review_required/ML_CHECK_PENDING`，不阻塞轻量 M1；T010 **accepted**，T020 **accepted**，T030 **accepted（Linux 核心）**。T040 **ready**；ML、ONNX、RKNN 和真实训练均未因 T030 执行。
