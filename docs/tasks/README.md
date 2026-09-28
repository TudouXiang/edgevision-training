# 任务索引

一次只领取一个任务。T000/T010 是 GPT6 本轮范围，其余是后续候选，前置未通过不得自动开工。实现后先标 review_required，经审查通过才 accepted。

|任务|执行者|前置|状态|
|---|---|---|---|
|T000 盘点与规范合并|GPT6|实际目标目录已确认|review_required，ML_CHECK_PENDING|
|T010 可启动骨架与精确契约|GPT6|T000相关轻量环境就绪|review_required，需补 A01–A04|
|T020 身份与项目|实现Agent|T010审查通过|blocked|
|T030 数据导入/校验核心|实现Agent|T020通过|blocked|
|T040 Worker与校验任务接线|实现Agent|T030通过、进程方案明确|blocked|
|T050 真实训练|实现Agent|T040通过、ML链路已核验|blocked|
|T060 ONNX/推理/部署包|实现Agent|T050通过|blocked|
|T070 管理端/端到端/实验|实现Agent，GPT6审查|T060通过|blocked|

若 T060 实际过大，可在相同契约内拆成导出、推理、模板包子任务；不借拆任务增加产品范围。T030不宣称已具备完整异步导入，接入完成由T040验收。

后续任务共用本包验收矩阵和完成记录，避免每份重复整套规范。
