# ADR 0013：T060 导出重建的分阶段契约

日期：2026-11-04 UTC。状态：实现设计已冻结，实际工具链/导出运行未验证；不构成E验收。前提为T050公开基线与ADR0012隐私准备。此次源文件是新重建，不恢复或冒用丢失候选的测试结论。

## 范围与兼容

先实现 E：可信PT → 固定ONNX导出 → checker/ORT及数值一致性 → 完整束发布和鉴权下载。I单图推理与P独立部署仍返回501，E的实际安全运行、故障矩阵及审查完成前不跨阶段。复用既有Job/Artifact表、单Worker/单重任务槽、guardian及drain receipt，不增加迁移或新队列。

来源只接受同项目、passed、来自succeeded训练任务的pt_best/pt_last，拒绝任意路径/URL/外部权重。提交、子进程复制和发布时重复核对源字节摘要、尺寸、严格训练元数据、类别及所属关系。冻结输入与代码/环境绑定，幂等重放返回原任务；归档/撤销/跨项目规则与训练一致。

## 固定目标协议（待新执行证据）

目标联合工具链保持公开T050的全部62包，规划新增ONNX1.23.2、ORT1.31.1及其必要依赖。新锁必须核对官方文件摘要和兼容性；依赖未实际装/测时能力保持不可用，不接受安装存在即available。

导出固定Linux CPU、YOLO11n、静态batch1、640×640、FP32、opset18、无图内NMS、无simplify；固定安全weights_only加载。原始图IR8是目标检查条件，禁止事后改IR版本冒充兼容。模型上限128MiB，解析前限额；递归拒绝external TensorProto、自定义domain/operator、functions/training_info/sparse及未知输入输出结构。目标IO为RGB float32 NCHW [1,3,640,640]、raw [1,4+nc,8400]，类别顺序严格绑定源模型。

导出器生成的原始图字节是发布候选；只允许剥离上游附加元数据后还原为同一原始图，不能悄悄转换/重写graph。checker和CPUExecutionProvider ORT必须验证同一最终字节，禁止fallback。固定零值、梯度、pattern三种公开可重建RGB张量，全部raw元素检查有限值及 `abs(ORT-PT) <= 1e-4 + 1e-4*abs(PT)`。阈值在实际执行前冻结，不为通过而放宽；这不是产品单图推理或正式精度证明。

E不依赖用户上传图片；协议常量可以公开，实际训练产物和运行证据的来源/摘要仅本地留存，公开报告只留匿名结果。

## 结构与发布

新增严格export输入/evidence/metadata版本，完整绑定job/run、冻结输入、源产物、原始和最终图、三个张量及精确runtime/provider。公开DTO不得借通用dict绕过ONNX元数据校验。

每次run隔离生成model.onnx、metadata.json、validation.json；正常退出不是成功条件。确认整树退出后重验来源及完整束，再intent → 同卷rename → 短事务登记Artifact并CAS成功。取消抢先则不得发布；孤儿不自动认成功，缺drain证据停领。失败只公开有界错误码与通用摘要。

新增独立delivery capability，实际受管探针成功且绑定仍匹配后才available；共享现有探针锁和恢复入口。API/Worker轻量进程不导入ML。下载按资源ID鉴权并通过同一已核验文件描述符有界流式返回。

## 需要的新证据

先做纯逻辑、隔离数据库及普通受管进程测试：权限/来源/参数/幂等/改哈希/缺产物/取消/Worker丢失/发布窗口/下载边界。UI覆盖真实队列状态、重复点击、刷新、断线和晚到请求。

实际ML须先具备经审查的非特权无外网执行边界，再确认原始图、checker/ORT、固定张量比较、真实HTTP受管链和浏览器。此前不能标记E accepted，也不能把mock或旧结果写成当前实测。回退先停新提交并确认活动任务退出，保留数据/产物，旧Worker不得接新export任务。
