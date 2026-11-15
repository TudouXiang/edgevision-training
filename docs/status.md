# 最新集成 · 项目导航与 PT 真实测试集测量（2026-11-15 UTC）

保留 main `eeb65ce` 已合入的项目工作台/管理区导航，不覆盖 UI 改动；本次增量加入独立 PT 评估及 `/proc` 退出竞态防护。普通源码 CI [#79](https://github.com/TudouXiang/edgevision-training/actions/runs/43672056388) 与显式隔离 [#80](https://github.com/TudouXiang/edgevision-training/actions/runs/43673168097) 全部选定任务通过。

[真实 PT 证据](evidence/T070-pt-only-evaluation-2026-11-15.md)：冻结的 20 张测试图，TP 5、FP 63、FN 15，precision 7.35%、recall 25%。这是新训练 1 epoch 模型的有限协议测量，分数偏低，不是 mAP 或模型质量验收。原生隔离、数据、依赖、训练、评估、清理及谱系校验均通过，不依赖 ONNX 导出。

真实模型 ONNX 严格导出仍受阻，GPU/NPU、正式精度/性能研究及整体验收仍未完成。远端集成不会自动升级 PEC/XiaoHu 部署；机器运行状态以对应实测记录为准。以下为历史检查点，不将旧收据当作新版本验收。

---

# 当前交付代码 · T070 工程链路重验，真实数据导出限制保留（2026-11-15 UTC）

本交付修订以 `8c83441` 产品代码为基线，后续只补证据文档。[#75](evidence/T070-final-backend-control-2026-11-15.md) 的十二阶段固定 Linux CPU 工程链路、普通 CI 与 Windows 进程回归均通过；这覆盖既有训练、导出、推理和独立源码包闭环，不代表任意模型可导出。

真实 Oxford 子集模型仍未满足原数值容差。最后一次同 checkpoint/同 ONNX 的 A/D 控制未找到合规修复，后端扫描已停止，未放宽阈值或更换产品参考。正式精度/性能及 Windows/CUDA/RKNN/NPU 模型验收仍未完成。**项目整体验收仍 open。**

用户机已部署版本仍为各自记录的 `57bc`；远端源代码更新不等于机器自动升级。升级后旧能力收据需重跑探测，不能复制沿用。XiaoHu 只读确认存在一个活跃管理员，API/Web 回环健康检查通过，不涉及密码验证。

以下保留集成前和历史阶段记录，以本节及对应精确证据为准。

---

# 当前增量 · T070 真实数据验证与交付边界（2026-11-15 UTC）

main 已隔离集成至 `57bc2b5`；本轮真实数据诊断位于功能分支 `feat/t070-real-cpu`，尚未合入 main。不要把下列分支证据当作 main 已有的新诊断能力。

真实 Oxford100 子集的一轮 CPU 训练、取消、受管 Worker 中断恢复及静默备份恢复已在隔离运行 [#67](evidence/T070-real-cpu-diagnostic-2026-11-15.md) 留证。该模型的 ONNX 导出仍未通过既有严格数值容差；[#71 分组诊断](evidence/T070-export-error-groups-2026-11-15.md) 记录了坐标偏差，不能等同于修复，也没有正式精度或性能结果。

PEC 与 XiaoHu 均有独立回环轻量部署记录，管理员由用户在本机交互初始化。XiaoHu 普通浏览器通过 5 项、ML 预期跳过 1 项；GPU 硬件可见不代表 Windows/CUDA 模型链路通过。服务检查是当时观测，不保证永久在线。

**项目整体验收仍 open。** [最新交付闸门](evidence/T070-delivery-gates-2026-11-15.md) 列出已验证与缺口；[演示/论文提纲](experiments/demo-and-thesis-evidence.md) 仅整理可引用证据，不伪造正式实验。以下原始阶段记录按各自日期与精确提交阅读。

---

# 当前增量 · T070 基础实验对比通过（2026-11-14 UTC）

精确 `0a204d9` 的 [#53 证据](evidence/T070-comparison-acceptance-2026-11-14.md)：866 后端、157 前端、三个 CI 任务通过；十二原生阶段全部通过，含两个真实训练任务的浏览器对比及 E/I/P 重验。修正了精确可访问标签问题，失败历史保留。

T070 整体未验收：main 隔离集成、用户机部署、正式实验及演示/论文材料继续推进。[Linux CPU 操作与演示手册](linux-cpu-guide.md)是说明，不是已部署证明。下方是历史检查点。

---

# 当前增量 · T070 管理员任务切片通过（2026-11-14 UTC）

精确 `a45421849c4b888be4ee01137c75de113b05d746` 的 #46 checks/Windows 均 success；后端 861 passed（14 原生 skipped）、前端 139 passed、契约一致；普通浏览器 5 实际通过、1 预期 ML 跳过。已补齐全局任务 API/分页/详情/日志/单任务取消，保留服务器鉴权与会话隔离。见 [精确检查点与限制](evidence/T070-admin-checkpoint-2026-11-14.md)。

T070 整体未验收：下一项为基础实验对比，另有正式实验、干净部署、演示/论文材料、main 集成与用户机验收。原生 ML 本次未重跑，每个实际环境须新鲜 probe。下方保留 P 及更早检查点。

---

# 当前增量 · T060 P 限定工程 accepted（2026-11-14 UTC）

公开 SHA `685f2efa56165fb5bd45641c81a1539ad94759ea`、tree `f3822aa07269b52407df203368b3ff7039802588` 的 #44 三个 CI 任务全部成功，schema 5 十二阶段全部 passed，含 E/I 重验、独立九依赖模型执行、HTTP 下载 ZIP 再执行及 P 专属浏览器闭环。独立审查支持固定 Linux x86_64 / CPython 3.12 / CPU / 可信 YOLO11n 的源码部署包工程验收。见 [P 精确证据](evidence/T060-package-acceptance-2026-11-14.md)和 [T060 分阶段报告](evidence/T060-report.md)。

本地普通回归 858 passed、14 原生 opt-in skipped、42 subtests passed；前端 130 passed，build/typecheck 通过。每个部署环境仍须当前源码绑定的 probe；源码 ZIP 不含解释器/wheels，初次安装需网络或另备 wheelhouse。每产物验证的是完整性，不声称所有未来产物均已独立执行。T070、正式精度/性能、Windows ML、GPU/NPU、完整原生故障矩阵及全项目交付未验收。

以下为历史检查点，旧的 P 未实现/未验收陈述仅适用于其对应版本。

---

# 当前增量 · T060 I 限定 accepted（2026-11-14 UTC）

精确公开 SHA `bd8d554b6bc51d05d6c1b81119ea8e1416eed5b9` 在工作流 #30 的 checks、Windows、隔离 ML 三任务全部通过，十阶段含真实 PT/ONNX 图片 HTTP/probe/浏览器全部 passed。原生运行与审查源码 tree 均为 `c21a8d54ee8222d7f9402ca08aa0bdb01cd2e47e`。独立需求映射审查支持 I 在固定 Linux CPU/YOLO11n 范围限定 accepted，见[精确证据](evidence/T060-image-acceptance-2026-11-14.md)。

P已实现固定源码ZIP、独立CLI及受管API/发布/下载接线，合成与受管进程测试不等于独立模型验收。生产P能力强制关闭（PACKAGE_SETUP_REQUIRED），probe/UI/原生验收待完成；T060 整体与 T070 未验收。Windows ML、GPU/NPU、正式精度/性能及完整原生故障矩阵不在本次通过范围。能力仍需各运行环境的当前源码 probe。

以下保留各阶段原始状态，不覆盖上述最新证据。

---

# 当前增量 · T060 I 源码审查通过、原生待验收（2026-11-05 UTC）

可信 PT/ONNX 单图推理的后端、前端和验证入口源码已分别通过独立审查。后端最终 d4e5f85：独立155项及8子测试通过；前端db38017：117候选测试及5项独立回归通过；隔离入口1dbb08b：198项通过、5原生跳过、34子测试，另30项准备链检查通过。各次审查范围见[I整合记录](evidence/T060-image-integration-2026-11-05.md)。

冻结整合 `069ac5efd50a1907bd29b48efae4d94ac4b8be78` 的完整 `scripts/dev.py check` 退出0：**646项后端通过、14项原生opt-in跳过，117项前端通过**，构建与契约漂移检查通过。14项跳过分别为原有E6项、训练3项、新I5项，均没有执行。普通API重启/Worker/整树退出在450b50f通过。首次整合及失败修复历史保留在下方对应报告，不覆盖旧结果。

I业务仍未accepted：真实I ML/ORT/probe/HTTP/浏览器全部NOT_RUN。新隔离验证源码固定v3十阶段，保持450秒共享模型预算、480秒外层执行和20分钟job；只有未来精确版本获准后才可执行。普通测试发现只证明默认5例、I专用1例可发现，实际执行均0。P仍501且blocked，T060整体及T070未accepted；E此前的限定验收保持原范围。没有新模型、用户图片、数据库或原始私有记录发布。

以下保留各阶段原始状态；旧文中 I 尚未实现只适用于对应版本，不覆盖本节源码状态。

---

# 当前增量 · T060 E 限定 accepted / I 待实施（2026-11-05 UTC）

固定 Linux CPU / YOLO11n 的可信 PT→ONNX 工程阶段已限定 accepted。证据严格区分：公开 `76af48f` 的真实七阶段隔离运行，以及 `7e322689` 的错误分类补丁与33项新增轻量/普通受管失败回归。独立审查确认正常模型执行路径没有改变；补丁版原生 ML 没有重跑。详见 [E逐项验收](evidence/T060-export-acceptance-2026-11-05.md)和[精确隔离运行](evidence/T060-isolated-ml-2026-11-05.md)。

I（PT/ONNX 真实图片推理）可进入设计与实施，P在I验收后实施；当前两者仍501，T060整体与T070未验收。新代码会使旧能力探针失效，实际运行能力仍须当前绑定的受管probe，不复制旧记录。Windows ML、CUDA、NPU与正式精度/性能仍未执行。

以下是对应旧版本和旧时间点的原始状态，不覆盖本节的新证据。

---

# 当前增量 · T060 隔离准备修正（2026-11-05 UTC）

复核识别并修正联网构建中 `pip check` 子解释器会执行安装后启动钩子的缺口。将依赖检查移到内核边界核验后的首个子阶段，保持 fresh venv、hash 锁与固定预算；见[修正验证](evidence/T060-preparation-bootstrap-2026-11-05.md)。当前源码检查点已持久备份，独立复核 accept（174 项聚焦测试通过）；最终本地整合回归为429后端通过/9原生跳过、47前端通过，构建/契约及HTTP重启通过；精确远端 CI 单独绑定发布 SHA 留档。真实 Docker/模型/ORT/ML 浏览器仍 NOT_RUN，E 未 accepted，I/P 仍 501。

以下保留各精确源码的历史验证结果，不能把旧静态方案或 CI 计数当作本次新候选的执行证据。

---

# 当前状态 · T060 E 重建候选（2026-11-04 UTC）

T050 的既有验收保持原范围。未发布的旧 T060 工作区已丢失，本轮从公开 T050 `3b5b8ec785be595dd82a15fe94adcb7d102396f2` 重新实现，**不沿用旧候选测试结果**。

E（可信模型 ONNX 导出）的后端、严格契约、前端和验证脚本已形成源码检查点，独立静态审查已收口，新一轮轻量整合回归为后端 356 passed/9 skipped、前端 38 passed，构建/契约通过；详见 [重建记录](evidence/T060-rebuild-recovery-2026-11-04.md) 与 [后端范围](evidence/T060-export-rebuild-core.md)。隔离 CI 的静态方案审查已收口，但实际执行仍未发生。最终源码与命令范围见 [检查点记录](evidence/T060-rebuild-checkpoints.md)。源码已按阶段提交并另存持久备份，不等同于完整项目交付或业务验收。

**真实 ONNX/ORT、ML HTTP/浏览器、容器隔离、Windows 新增 E 行为均未执行，E 未 accepted。** 默认自动工作流暂不运行真实 ML；隔离方案须完成审查并获准后才能实际验证。I（真实图片推理）与 P（独立部署包）继续保持规范化 501，不越过 E 验收闸门。没有发布图片、模型权重或原始运行证据。

公开源码 `0455566` 已通过 [Linux/Windows 普通 CI](evidence/T060-source-ci-2026-11-04.md)，ML job 明确跳过。此结果不解除 E 原生验收闸门。

浏览器证据计数另有独立修正（静态复审与轻量整合回归已通过：371 后端/9 跳过、47 前端，增量远端 CI 已通过，详见下方精确版本）：匿名 schema v2 区分执行、跳过、未运行与重试，不再把所有回调写成 completed；[验证记录](evidence/T060-browser-evidence-counts-2026-11-04.md)。公开提交 `b9cbc568774d8ddfdfb4a312009ebf39bebe4437` 的 [CI 41871285873](https://github.com/TudouXiang/edgevision-training/actions/runs/41871285873) 已完成 success：普通浏览器实际执行 4 项通过、1 项 ML 跳过；Linux 371 后端/9 跳过、47 前端，Windows 既有进程/API 通过；ML job skipped。不推进 E/I/P 验收。

以下保留历史阶段记录；遇到差异以本节为准。

README/验收文档的当前与历史范围已校正，并新增[纯合成 SQLite WAL 恢复练习](evidence/synthetic-backup-recovery-2026-11-04.md)。本轮端点差异独立复核 accept，27 项新增文档/合成恢复测试通过；整合轻量回归为 **398 后端通过、9 原生跳过、47 前端通过**，构建/契约及真实 API 重启探针通过。恢复练习只覆盖固定临时样本，不是生产备份工具或全平台恢复验收；真实 E/I/P 的边界不变。各远端结果仍以对应精确发布 SHA 为准。

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

## 2026-11-15 工作区导航增量（review_required）

项目新增明确进入入口和数据集/训练/实验对比/导出/推理/部署分区；系统、账号与管理员功能从业务主流程分离。返回列表保留当前项目组件，切换项目沿用原隔离清理。159 项前端测试、构建、E2E 类型检查以及 Windows 临时环境 5 项真实浏览器回归通过，1 项 ML 用例按预期跳过。未重跑 ML/GPU 链路、未部署到现用实例；详见 `evidence/2026-11-15-workspace-navigation.md`。
