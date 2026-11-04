# T050：真实YOLO训练闭环

执行者：实现Agent。前置：T040 accepted、可信资产和目标ML环境核验；状态 accepted（固定 Linux CPU 小规模真实训练闭环；完整平台与发行尚未验收）。

项目原创代码/文档已选择 AGPL-3.0-only，见 [ADR 0010](../adr/0010-project-licensing.md)；计划采用 Ultralytics AGPL 路线。精确联合 ML 环境、固定官方权重和本地样本已完成[前检](../evidence/T050-preflight-2026-11-04.md)，不能用根 LICENSE 代替资产授权。COCO8 的 GPLv3/CC BY 4.0 差异仅允许当前私有本地技术验证，不再分发。可选 ML hash lock 与真实训练已接通；最终公开验收使用项目生成的合成图，不分发 COCO8。

先按 [ADR 0011](../adr/0011-t050-fixed-training-adapter.md) 实施：复用现有 guardian/状态机/0003_worker，不新增框架或迁移；冻结完整输入，独立运行副本，固定安全加载，真实有界指标和双 PT 原子发布。独立 1 epoch 烟测单独记录，不能代替平台验收。Windows ML、CUDA 与 ONNX 均未验证。

目标：只接入已锁定YOLO11n目标检测，参数白名单、真实日志/轮次/指标、权重登记与输入/环境快照。先完成小规模烟测，正式实验单独授权。

不做：全部YOLO系列、修改训练框架、自动调参、恢复/暂停训练、无限制kwargs、多GPU。

验收：使用明确来源的小样本实际训练并产生可读PT；seed/类别/数据摘要/权重摘要/环境/参数可追溯；失败、取消、设备不可用、磁盘不足与产物缺失正确处理；显示的指标来自实际事件。Worker串行与权限继续通过。

测试替身可以测接线，不能替代A11的真实任务证据。正式实验的轮数/预算由独立计划约束；不要为凑结果持续训练。输出docs/evidence/T050-report.md与实际任务清单。

## 2026-11-04 实现记录

固定适配器、完整冻结输入、真实指标、双 PT 发布/下载、操作员探针、训练表单及故障测试已实现。
本地真实 Uvicorn/Worker 单轮 CPU 合成数据烟测通过；尚待最终代码 aggregate、独立复核及远端 Linux/Windows/浏览器 CI。
以上为 CI 前的实现记录。最终结论 accepted 的范围见 [CI 验收](../evidence/T050-ci-acceptance-2026-11-04.md)，不能扩展到 Windows ML、CUDA、正式精度或 ONNX。
