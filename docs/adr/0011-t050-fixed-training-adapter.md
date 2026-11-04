# ADR 0011：固定 YOLO11n 训练适配器与原子产物束

- 日期：2026-11-04 UTC
- 状态：accepted（本阶段设计决策，允许限定实现）；实现、A11/A12 及发行验收 **未完成**
- 代码基线：`3795759fbb2474f4639f427ff3c69a31a1c6bb69`；T040 accepted 的实测边界不扩大
- 前置证据：[T050 前检](../evidence/T050-preflight-2026-11-04.md)；许可沿用 [ADR 0010](0010-project-licensing.md)

## 现实、目标和最小方案

现有 `TrainParams`、Job/Artifact/metrics 表已覆盖首版训练资源，但 `worker.process`、
`task_process.execute`、`runner_protocol` 和 `publication` 只支持 dataset_check；训练 HTTP 仍 501。
现有 `job_public` 不返回冻结输入，metrics 表尚无真实训练写入。不能把 DTO 或临时 ML 环境当成接通。

决定在现有受管进程协议中增加一个固定 train 分支：小型 `training_runner`、私有严格协议和
训练发布函数；复用 T040 guardian、GO、drain receipt、单槽、取消 CAS 和恢复策略。
不增加调度框架、插件注册表、状态机、数据表或迁移。现有 `0003_worker` 足够存储版本化 JSON、
metrics、PT Artifact。若实现发现约束不足，须先补充本 ADR，不绕过约束写第二套存储。

更小的替代是只跑命令行训练而仍让 API 返回 501，足以验证依赖，却不能满足 A11 的平台闭环。
另一方案是独立 ML 服务/新队列，增加进程与一致性边界且违反单机基线，拒绝采用。
用户已授权自主选择实现与许可；不新增付费服务、商业协议、硬件或正式长训练承诺。

## 1. 依赖和固定资产供给

候选为 Linux Python 3.12.14、Ultralytics 8.4.202、Torch 2.15.0+cpu、torchvision 0.29.2+cpu。
前检 62 wheel 联合闭包保留全部 33 个 backend lock 的精确版本与 wheel hash。实现需把经过审查的
可选 ML 安装入口及完整哈希锁纳入仓库，默认 API/轻量测试不安装或 import Torch。
前检锁是可复现证据，尚不是已发布的生产依赖方案；其它平台不得套用 Linux wheel/hash 冒充支持。

能力探测不由 HTTP 请求启动，也不在 API/Worker 主进程导入 ML。受控的操作员安装/探测命令在固定、限时、可清理的自有子进程执行，记录实际隔离范围；输出严格版本化的能力记录，绑定解释器、精确依赖、适配器代码和模型 manifest/hash。API 只做轻量绑定核验，记录缺失、过期或失败则不可用。每次训练仍在受管 child 中重新校验真实设备和全部绑定；缓存探测不是运行成功证明。不接受客户端或配置任意指定探测可执行文件。

只接受服务端固定 `yolo11n.pt` 标识；供给命令使用固定官方发布 URL、release/asset ID、
预期 size/SHA、来源/许可 URL 和版本化 manifest。正式任务不联网补下载、不接受用户路径/URL/PT。
权重缺失、哈希不符或供给 manifest 不受信任时能力不可用且拒绝创建，不自动找同名缓存。
每次运行复制并核验固定基础权重，冻结完整 manifest 哈希及实际权重哈希。
本次已核验权重为 5,613,764 bytes，SHA256
`0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`。
官方旧资产没有 publisher digest；本地哈希证明一致性，不冒称签名真实性。

COCO8 仅限当前私有本地烟测。压缩包 GPLv3 与文档 CC BY 4.0 标识冲突、单图权利未逐个确认，
不得加入仓库、发行包、演示下载或换成项目许可。真实用户数据也不得自动外传。

## 2. 不可变提交和运行副本

提交 train 在现有鉴权事务内验证同项目、ready Dataset、未归档项目、白名单参数与环境能力。
保持 Idempotency-Key 的原有范围、同参重放和异参 409；重放不刷新原输入。新训练总是新 Job。
冻结：Dataset ID/version、ZIP SHA、snapshot key、规范化完整文件清单及其摘要、报告 Artifact ID/
size/SHA、类别顺序、split counts；基础权重供给 manifest/hash；显式解析后的全部训练参数。
不要只保存 `dataset_id` 或事后读取可变的当前 report 指针。内部路径不进入公共 DTO。

GO 后 child 验证报告/manifest 与每个源文件的 size/hash，然后独立复制图片/标签到 run 私有目录，
再次核对副本。禁止硬链接、可写共享目录和链接逃逸。
运行前按冻结清单估算独立数据副本、基础权重、双 checkpoint、缓存和余量的磁盘预算，设置显式输入/输出上限；不足拒绝，运行中 ENOSPC 正确失败，不能借硬链接规避容量要求。训练仅使用新生成的规范 YAML，固定 train/val、
names/nc 和 run 内路径，不直接把上传 YAML 交给 Ultralytics。所有源路径必须通过既有安全解析。
Ultralytics 即使 cache=False 也写 labels cache，故源 ready snapshot 永不作为训练工作目录。
框架还可能拒绝小于 10px 的图片、跳过样本、去重标签或修复 JPEG；必须比对实际使用的样本集合/类别/数量与冻结输入，拒绝静默漂移，并在训练后核对 run-local 源图片/标签字节未变。
发布前再次核对冻结输入；训练异常、取消或恢复中断绝不能把 ready Dataset 改成 pending/invalid。

## 3. 运行时边界与安全加载

Torch/Ultralytics 只能在固定 child 收到 GO 后导入；API、Worker、guardian 不导入 ML。
不更改 framework 安装源码。适配层可做经过版本/源码契约核对的进程内小范围适配，版本不匹配即拒绝。
保留隔离 HOME/TMP/配置、无凭据环境、关闭 telemetry/integrations/autoinstall/AMP/绘图、workers=0、
固定单设备和线程上限；禁止自动 CPU 回退、多卡/DDP、resume 和用户任意 kwargs。

已核对版本的 check_det_dataset 无条件调用 check_font；plots=False 本身不能证明离线。
可仅在明确 plots=False 的固定适配器中禁用无用途字体发现，配合审计并测定没有字体下载/子进程。
严禁关闭网络审计来使烟测通过。Python 审计阻止 socket/DNS/subprocess 的限制必须明确：
它不是原生代码或操作系统级沙箱，不能声称绝对无网络。发现任何未预期尝试应失败并留脱敏原因。

只在已核验固定基础 PT 或本 run 产生的明确 best/last 路径执行加载。所有读取，包括 final_eval、
strip_optimizer 和训练后验证，都必须强制 weights_only=True；只注册事先审查的固定类名单，
不得从 checkpoint 内容动态导入任意类或失败后 fallback unrestricted load。未知类/格式直接失败。
该版本 strip_optimizer 会捕获加载失败并返回空字典，故还须断言最终 checkpoint 的 optimizer/训练状态已按固定导出契约处理，不能只信 train() 返回或文件可读。
安全加载不是允许任意 PT 的理由，用户上传 PT 仍禁用。

## 4. 参数、真实指标与有界日志

沿用 TrainParams 的既有限制：YOLO11n、epochs 1–100、batch 1–16、imgsz 320/640、
seed 0–4294967295、learning_rate 1e-6–0.1。额外字段拒绝，实验名称只作显示不参与路径。
CUDA DTO 可解析不表示能力可用；本阶段只放行实测 CPU，CUDA/Windows ML 未验证明确不可用。
使用显式固定 optimizer（首版 SGD），将 learning_rate 映射到 lr0；缺省解析为固定有记录的值，
不能用 optimizer=auto（该版本会忽略用户 lr0）。保存实际有效 optimizer/lr0、schedule、warmup、
nbs、seed、线程、设备、框架版本、代码版本和锁哈希，不仅保存用户输入。
该版本可在首轮 OOM 自动减半 batch，并在 NaN 恢复中重放 epoch；适配器须在 train-start/每轮 start 验证 device/batch/epochs/resume 不变，使用 epoch-start latch 拒绝重复尝试。框架保存还可能修复 EMA 和 nan_to_num，故在 epoch-end 保存之前检查 loss、live/EMA tensor 有限性，固定版本 save_model 的进程内包装须在原方法之前检查实际参数/指标和 live/EMA tensor 的有限性及 FP16 可表示性，避免有限 FP32 转半精度溢出后被 nan_to_num 掩盖。记录不可清除的 fatal latch，并在产物证据前复核；不能让吞异常/自动修复掩盖失败。安全策略异常可使用专用 BaseException，只在最外层适配边界显式捕获并映射稳定失败码，防止框架 except Exception 降级为警告。实际 optimizer 更新见证用 optimizer.register_step_post_hook，不使用该版本未调用的 optimizer_step callback。
烟测的 nbs=1、warmup_epochs=0、lrf=1.0 仅为有限 batch 更新验证，不自动成为产品默认值。

固定 callback 生成严格结构化事件，绑定 job/run、单调序号、真实 epoch 与有限指标白名单。
train/val loss、precision/recall、mAP50/mAP50-95 仅在框架实际提供有限数值时记录，缺值保持缺失/null，
不填 0，不从 stdout 正则推算，不使用计时器进度。已完成 epoch/总数可生成真实进度。
该版本 final_eval 会在 best 验证后把 trainer.epoch 加一并再次调用 on_fit_epoch_end；因此必须用
明确 epoch 训练阶段标识过滤 final-eval，而不是只按 (epoch,name) 去重或截断到总轮数。
final-best 验证结果可单独放模型 metadata，不覆盖最后一轮曲线。

Worker 验证事件绑定、名称/类型、有限数值、epoch 范围、单调性和文件大小。数据库以
(job_id,epoch,name) 去重；metrics 与对应 job_events 在一个短事务写入，重读不追加重复事件。
上限可按 100 epochs × 固定指标数导出并加严格字节限制，超限错误不能无限读写。
日志继续复用既有 512 KiB/2000 条、单条 2048 bytes、响应 64 KiB/500 条限制和脱敏。guardian 当前只认识固定校验日志，需扩展严格事件 envelope，不能直接放行任意 stdout/JSON。
整树退出后必须做最后一轮事件读取，不能漏掉尾部指标；训练成功还需要完整产物证明。

## 5. 完整 PT 束、取消和发布

训练结束及 final_eval/strip_optimizer 完成后再加载 best.pt 和 last.pt，核对 detection 结构、
类别数量/有序名称与训练输入一致、文件非空/可读；记录最终 size/hash。不能提前哈希后续还会变化的 PT。
child 只把 best.pt、last.pt 和严格 metadata/manifest 放入 bundle；缓存、日志、run-local 数据和
任意框架额外输出不作为发布产物。证据绑定 job/run、输入摘要、参数/环境与全部输出；拒绝重复/越界/
特殊文件、缺文件、未列出的文件、错误格式和错 hash。两份权重不可部分发布。

必须收到可信 drain receipt 且确认 guardian 退出后，Worker 才做轻量文件/证据再核验。
固定训练发布函数沿用 T040 两阶段：记录 intent → 同卷原子 rename 整个 bundle → 一个短事务同时
插入 pt_best/pt_last 两条 Artifact 和 CAS running→succeeded/status event。
取消先赢则不登记任何 PT；成功先赢则返回已有 succeeded。崩溃遗留束隔离且无可下载记录，
恢复不从孤儿目录重建成功。失败必须确认整树退出后终结，不发布可用 PT，不改 ready Dataset。
Artifact passed 仅表示本阶段 PT 结构/加载校验，不代表 ONNX、精度达标或部署可用。

## 6. API、UI、兼容和回退

实现只放开现有 POST jobs 的 train 分支。通过 Pydantic 增量加入可空、版本化、白名单化的
训练 provenance（Job detail 与 PT metadata），展示摘要/资源 ID/参数/环境，不泄露本地路径、
原始环境变量、密钥或 traceback。所有读取、日志、指标和下载仍沿 Project owner/admin 鉴权。
下载 best/last 依据 Artifact ID，校验 regular file、size/hash，保持现有报告下载不回归。
大 PT 下载不得照搬报告 16 MiB 上限或一次性无界读内存，需显式模型上限和受控传输。校验与响应必须持有同一文件描述符/handle，不能 hash 后按路径重新打开未经核验的文件；取消响应正确关闭 handle。

UI 增加 ready 数据选择、真实能力说明、受限参数表单、任务状态/取消、真实曲线、两份 PT 下载与
provenance；缺指标显示无数据，刷新从快照+游标恢复，终态最后拉取，错误/无权/归档均测试。
生成 OpenAPI/TS，不手改生成类型；旧消费者可忽略新增可空字段，不改变已有状态枚举/游标语义。

无 schema 迁移。回退前停止提交并让活动任务终结或按已有协议取消、确认 drain；保留库、产物和
审计记录，关闭训练能力/恢复 501，不把 train queued 留给旧 Worker 自动失败。回退不能删除历史
Artifact 或覆盖 ready Dataset，也不自动降级库或更改已发布许可。

## 7. 实现与验收清单（全部待执行）

1. 轻量环境跑 `bash scripts/dev.sh check`，并核对无 Torch 导入；生成契约再执行漂移检查。
2. 严格提交、缺权重/错 hash/缺 ML、未 ready/跨项目/归档/越权、幂等冲突、非法 kwargs/设备测试。
3. 真复制隔离测试：训练写 cache 后源 snapshot、报告和文件清单不变；替换/逃逸/损坏输入失败。
4. 事件测试：重复 callback、final-eval epoch+1、非有限值/坏绑定/超限/尾事件，不产生假值或重复曲线。
5. 两 PT 完成后安全加载/最终 hash；缺 best/last、坏 PT、未知 safe class、额外输出或进程非零均失败。
6. 排队取消不导入 ML；运行取消/Worker crash/发布各窗口故障，沿 T040 receipt/CAS 证明唯一终态、
   无部分发布和无遗留占用。缺 receipt 继续停领，Windows 既有安全限制不放宽。
7. 单槽混合 dataset_check/train 排队，训练失败不破坏 ready Dataset；跨用户 PT 下载/日志/指标拒绝。
8. 先独立 Linux CPU 1 epoch、batch=1、imgsz=320、seed=0、最多 4 train+4 val 样本、硬超时，
   保留过程日志、有效参数、最终 PT/hash 和安全加载/网络审计结果；这仍不是 A11。
9. 再通过真实 API 上传/校验/提交 → Worker → 真实 callback → 双 PT → 鉴权下载闭环，记录 Job/
   Artifact ID 和冻结输入。真实浏览器测表单/取消/刷新/断线/无数据/下载才可申报平台 A11/A12。
10. Windows ML、CUDA、ONNX/ORT、RKNN/NPU、主机断电、正式精度实验均单独记录为未执行。

精确新增测试文件/命令与失败分支须在实现报告列明；不把以上计划当成已运行。
手动读取并执行 arch-spec/experiment-evidence 工作流，不声称宿主自动触发 Skill。

## 实现补充：探针与可下载文件隐私

能力只来自显式操作员固定探针：同一联合解释器、受管子进程、GO 与有界退出确认，绑定解释器、安装 distribution RECORD 指纹、适配器源码、锁文件和基础资产清单。API 只读取并核对轻量绑定，不启动或导入 ML；每次真实训练子进程重新检查版本和设备。探针状态也必须留存并在 Worker 启动前核对退出，避免操作员进程中断后重叠运行。训练重试可带同项目 train 类型的 source_job_id，仍新建任务与输入快照。

下载 PT 也可能携带 train_args、模型 args、原始路径及 Git 元数据。发布前以固定 detection checkpoint 字段重建安全元数据，只保留重载必需结构和白名单参数，移除路径、URL、Git、结果历史和其他非必要字段。仅操作已知模型顶层固定属性，不遍历任意对象图；对最终净化字节再次 weights-only 加载、结构/类别检查、哈希。

数据一致性除样本文件名外，还核对框架实际标签类别和框数量/数值，拒绝去重、忽略图片、修复 JPEG 等隐式变化；框架建管线后和训练结束均核对运行副本原文件摘要。指标单独使用有界 JSONL，不挤占 stdout 日志配额；最终证据绑定指标文件哈希与数量，数据库指标、事件和读取偏移同事务提交。
