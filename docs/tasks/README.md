# 任务索引

一次只领取一个已放行的任务，前置未通过不得自动开工。实现后先标 review_required，经审查及所需实际验证通过才 accepted。下表汇总本分支已有任务单与证据，不替代[项目状态](../status.md)和[验收矩阵](../acceptance.md)；历史计数不能当作新提交的测试结果。

|任务|执行者|前置|状态|
|---|---|---|---|
|[T000 盘点与规范合并](T000-inventory.md)|GPT6|实际目标目录已确认|历史盘点保留 review_required / ML_CHECK_PENDING；后续环境验证见对应阶段证据|
|[T010 可启动骨架与精确契约](T010-skeleton.md)|GPT6/Codex|T000相关轻量环境就绪|accepted；Windows A01–A04 与[独立审查](../evidence/T010-change-review-2026-09-29.md)|
|[T020 身份与项目](T020-auth-projects.md)|实现Agent|T010审查通过|accepted；[Linux 真实浏览器验收](../evidence/T020-browser-acceptance-2026-11-04.md)|
|[T030 数据导入/校验核心](T030-dataset-core.md)|实现Agent|T020通过|accepted（Linux 核心）；[三项浏览器回归](../evidence/T030-browser-acceptance-2026-11-04.md)|
|[T040 Worker与校验任务接线](T040-worker.md)|实现Agent|T030通过、进程方案明确|accepted（已实测范围）；[跨平台验收与限制](../evidence/T040-cross-platform-acceptance-2026-11-04.md)|
|[T050 真实训练](T050-training.md)|实现Agent|T040通过、ML链路已核验|accepted（固定 Linux CPU 小规模闭环）；[验收与限制](../evidence/T050-ci-acceptance-2026-11-04.md)|
|[T060 ONNX/推理/部署包](T060-onnx-deployment.md)|实现Agent|T050通过|E 重建候选 review_required，未 accepted；I/P 仍未实现；[检查点与证据](../evidence/T060-rebuild-checkpoints.md)|
|[T070 管理端/端到端/实验](T070-final-validation.md)|实现Agent，GPT6审查|T060通过|blocked；不得越过 T060 accepted 闸门|

T060 按同一契约内的 E（导出）、I（推理）、P（模板包）顺序推进，不借拆任务增加产品范围。普通轻量 / 浏览器 CI 不替代真实 ONNX / ORT、隔离模型执行或 ML 浏览器验收；正在执行的验证以项目状态和新增证据为准。

后续任务共用本包验收矩阵和[证据导航](../evidence/README.md)，避免每份重复整套规范。T030 核心与 T040 异步接线分开验收，不能将任一阶段的范围扩大为完整平台完成。
