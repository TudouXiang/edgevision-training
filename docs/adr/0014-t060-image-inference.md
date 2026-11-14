# ADR 0014：T060 I 可信 PT / ONNX 单图推理

当前状态（2026-11-14 UTC）：I 在固定 Linux CPU/YOLO11n 范围限定 accepted。精确 SHA `bd8d554` 的原生十阶段、普通 checks 及 Windows 进程任务全部成功；独立审查需求映射通过。P 可进入独立设计实施，尚未验收。见[I精确验收](../evidence/T060-image-acceptance-2026-11-14.md)。

以下保留设计冻结时的原始候选状态和约束，旧“尚未接通”只描述设计阶段，不覆盖上方源码进展。

日期：2026-11-05 UTC。状态：**设计候选，等待独立设计审查；尚未接通业务入口**。
基线：`0d40ffedc7ed5635f21ff4bb00d449987f90e24d`。E 已在固定 Linux CPU / YOLO11n
工程范围限定 accepted；76af 的原生证据和 7e322689 错误协议增量审查不是本次 I 的运行证据。
已手动读取 arch-spec、feature-delivery、experiment-evidence Skills，并对照实际源码。
本记录收敛先前 proposed I/P 草案，**只冻结 I；P 继续 501，T070 不实施**。

## 1. 决定、替代方案和授权边界

复用 `0003_worker`、Job / Artifact、全局一个 Worker 重任务槽、guardian / GO / drain receipt、
publication intent → 同卷 rename → 来源行精确比较与 CAS。没有新数据库迁移、队列、服务或任务状态。
只接受平台成功训练的 passed PT，或同项目成功 E 的 passed ONNX；不接受外部权重、路径、URL、脚本。
API 和 Worker 主进程不导入 Torch、ORT、NumPy，不在 HTTP 中解码图片。

更小兼容方案采用既有图片上传占位接口：仅保存不可变原字节为 `inference_input / unverified`，
真实 verify / decode 放入 infer 受管子进程。即使某次推理成功，原输入始终保持 unverified；每个成功结果
独立持有净化 preview 与 decode 事实。多个任务引用同一输入，失败、取消或中断不改变其他任务和原输入。
不新增 image_check Job，不伪造上传 Job 来适配非空 `idempotency_keys.job_id`。
上传不承诺幂等；infer 提交沿用 Idempotency-Key。未选 API 同步解码/推理、第二队列及两套后处理，
因为分别绕过执行槽、扩大迁移和引入协议漂移。

本次允许轻量源码/测试；真实 Torch、ORT、模型下载、能力 probe、图像原生模型烟测均 **NOT_RUN**，
必须以后针对精确 SHA、审查过的无外网非特权边界另行放行。Python audit hook 不是网络 sandbox。
无新依赖、系统安装、推送、main 修改或公开资产。开发依赖链接不入 Git。

## 2. 公共接口与严格 DTO

### 上传

`POST /api/v1/projects/{project_id}/images`：恰好一个名为 `file` 的 multipart part。
成功 201 只返回严格 `InferenceInputArtifactPublic`：kind=inference_input，job_id=null，
format=jpeg|png，metadata_schema_version=1，validation_state=unverified；metadata 为
`{schema_version:1, declared_format:jpeg|png, validation_scope:bounded_upload_bytes}`。
不返回原文件名、路径、未解码宽高或伪验证信息。

- 文件 `0 < size <= 50 * 1024 * 1024`；body 上限为该值加 `128 * 1024`。
- 原始 ASGI 流按真实累计字节限制，边读边 SHA-256；不能信任 Content-Length 或先无限 spool。
- boundary 非空且 <=200 字节；<=8 个 part header，每个 <=4096 字节；拒绝重复
  Content-Disposition / Content-Type、额外字段/part、非法或超过20字符的 Content-Length、截断。
- 文件名为无控制字符的简单 basename，含扩展名 <=160 字符；小写规范化扩展名仅 jpg/jpeg/png。
  JPEG MIME=image/jpeg 或 application/octet-stream；PNG 对应 image/png 或 octet-stream。
  扩展名/MIME 只是声明，真实格式由 runner 校验。
- 复用现有 multipart 算法，提取固定策略 helper；dataset ZIP 原有限额/错误码不改变。
- 读取 body 前验证 Origin、CSRF、会话、归属和 active；持久化完成后短写事务再次全部验证。
  新生成 `.part` 独占创建，flush/fsync；同卷发布 `images/{artifact_id}/source.jpg|png`。
  同一已核验文件身份、size/hash 才能登记。拒绝 symlink、特殊文件和根逃逸。
- 登记失败不返回成功；未注册 .part / 孤儿仍隔离，不能重建成功或删除被其他记录引用的文件。

### 任务、结果与下载

`POST /projects/{id}/jobs` kind=infer，params 仅
`model_artifact_id/image_artifact_id/backend/confidence/iou`；backend=pt|onnx；confidence/iou 为
有限严格数值 [0,1]（拒绝 bool、字符串、NaN/Inf），默认 0.25/0.45；额外字段拒绝。
可空 `source_job_id` 只允许同项目 infer 终态，映射既有 retry_of_id；重试创建新任务且重新校验输入。
幂等摘要包括规范化 params 和 source_job_id。归档后允许已存在同键重放及历史读取，不允许新任务。
JobPublic 新增可空 `inference` 摘要：模型/图片/源 Job ID、原字节 hash、params、协议、runtime/code 绑定，
不公开内部路径；package 字段不在本次添加。202 只意味着队列接受。

`GET /inferences/{id}` 的 id 为 **inference_result Artifact ID**；响应 artifact_id 同样是结果 ID。
返回 image_width/image_height、backend/provider、classes、params、protocol、detections、preview 的
width/height/sha256 和相对鉴权 image_url；这些宽高和坐标都以 EXIF 校正后的图为准。
新增 `GET /inferences/{id}/image` 返回该成功结果的净化 PNG；Artifact 现有列表/详情及 download
提供 result.json。原 unverified 输入不提供原字节下载/preview。不存在额外推理列表接口。

从 OtherArtifactPublic 移除 inference_input/inference_result，新增严格 kind 分支；P 尚未产生数据且仍501，
不在本次收紧 deployment_zip 或实施任何 Package schema。新增公开/内部 schema：
InferenceInputMetadata、InferenceJobSource、PreprocessRecord、InferenceRuntime、InferenceProvenance、
InferenceDocument、InferenceResultMetadata、FrozenInference、InferenceInput、InferenceEvidence、InferenceProbeRecord。
全部 extra=forbid；严格 scalar、有限数值、SHA格式、长度/数量限制，以及 job/run/source/image/classes/
params/result/preview 交叉验证；坏 metadata 不能落通用 dict。document 不含最终 Artifact ID，读取时补 DB ID。
OpenAPI/TS 由既有脚本生成，禁止手改；前端仅消费生成类型。

## 3. 来源和不变性

PT：同项目 pt_best/pt_last、format=pt、passed、成功 train Job。复用 `export_inputs.source_snapshot`，
核对原始训练 metadata、完整训练 publication、dataset/report、类别、源 size/hash。
ONNX：同项目 onnx/passed、成功 export_onnx Job；提取 `export_download` 完整 E publication/metadata/
validation 绑定核验为非 HTTP helper。核验严格 FrozenExport，父 PT 和训练来源，并核验所有发布成员。
backend 与模型 kind/format 必须一致，不自动转换、换模型或 fallback。
图片必须同项目严格上传 metadata 的 inference_input/unverified，job_id=null、服务器生成 storage key。

FrozenInference 使用模型 backend 判别的严格来源结构，保留 PT 训练源快照或 ONNX E 快照、完整源 metadata
及摘要、图片原字节摘要/size/format/key、params、当前 runtime/code/protocol；所有引用交叉绑定。
提交在只读快照中验证来源/大文件 hash，再短 BEGIN IMMEDIATE 重复鉴权、归档、幂等及已核验 DB 行精确比较；
不得持 SQLite 唯一 writer 做长 hash。infer 使用 E 式两阶段入口。

runner 用已检查 regular/no-symlink/root containment 的**同一打开描述符**做有界复制，fstat 与打开前身份相符；
至冻结 size 后多读1字节检测增长，复制流同时 hash，只解析 run 内 copy。复制后再次验证原来源。
发布前重验来源、DB 关系、run 内 copy；rename 后重验完整目标束，最终短事务比较 frozen/params/code/run/
publication 与来源行。不同步的任何证据都失败。管理员可改同 OS 用户文件的风险不由 hash 当作签名解决。
下载核验完整历史发布与文件，再从同一验证过的描述符有界返回，断线释放；不 hash 后重开。
历史读取不要求当前能力 probe 有效，代码升级不能破坏已发布历史的协议校验。

## 4. 同一算法源：detection-image-v1

`backend/app/delivery_infer.py` 是唯一 decode/preprocess/postprocess 源；不导入 app、数据库、FastAPI，
模型依赖仅函数内 lazy import。未来 P 按原字节复制该文件，不维护第二套算法，也不动态拼装源码。
平台安全 PT loader 在独立适配器；共同源包含独立 ORT 图/IO/执行入口所需固定逻辑。

### Decode 与摘要

只允许 JPEG/PNG，实际 format 与声明一致，单帧，宽高 >0、总像素 <=30,000,000。
Pillow verify 后重新从同一受控 copy 完整 load；截断、坏图、动画、多帧、解压炸弹 warning 均失败。
固定 Pillow12.3.0；支持 RGB/L/RGBA/LA/P；其他模式（含 CMYK、高位深）明确失败。
EXIF transpose 恰好一次，orientation 缺失记1；非严格整数、1..8之外或 EXIF 无法解析均 IMAGE_DECODE_FAILED。
RGB/L/P 中的 tRNS 和 RGBA/LA 的 alpha 均先转 RGBA；灰度复制三通道。每通道合成规则固定
`floor((source*alpha + 114*(255-alpha) + 127)/255)`，alpha为0..255整数；无透明信息则直接转RGB。
不做隐式 ICC 色彩管理。preview 不含 EXIF、ICC、注释等元数据。

I 内所有 `image_sha256/image_size_bytes` 永远指上传原 bytes；`frozen_input_sha256` 专指完整 FrozenInference
canonical JSON 摘要。禁止在 I 新结构中使用含义不明确的 input_sha256；仅嵌入的既有 E 结构保留其历史语义。
encoded_width/height 是码流原尺寸；image_width/height、全部检测框是
EXIF 校正后的尺寸；另存 RGB 原始像素、模型输入张量、preview 独立摘要，互不代替。原输入不回填尺寸。

### 整数 letterbox

固定 640×640、batch1、RGB、NCHW、FP32、除255，Pillow BILINEAR，允许 scaleup。
`r=min(640/w,640/h)`；`new_w=max(1,min(640,floor(w*r+0.5)))`，new_h 同理；
`left=(640-new_w)//2`，`right=640-new_w-left`，top/bottom 同理，padding=114。
记录整数 new_w/new_h、四边 padding、`scale_x=new_w/w`、`scale_y=new_h/h`；逆变换使用实际各轴比例，
不用理想 r。禁止 auto stride、stretch、dynamic。张量/raw hash 使用 little-endian FP32、C-order。

### Raw / NMS / 结果

raw 恰为 float32 `[1,4+nc,8400]`，所有元素有限；前4为输入空间 cx/cy/w/h，后面为 [0,1] 类别 score，
无 objectness，不重复 sigmoid。每 anchor 最高类，tie 取最小 class_id；保留严格 `score > confidence`。
非正 w/h 丢弃，有限越界坐标允许后 clip；非有限值或非法 score 使整个任务失败。
候选按 `(-score,class_id,anchor_index)` 稳定排序，最多3000；类别内 NMS，在 padded 模型空间恰好一次，
IoU 严格大于 iou 才抑制，最多300结果。没有时间截止后悄悄返回部分结果。
之后减 padding，除各轴实际 scale，clip `[0,w] / [0,h]`，删除 clip 后零面积框。
最终严格 class_id 范围、有限 score [0,1]、`0<=x1<x2<=w` 及 y；空检测 `[]` 是真实成功，不造框。
记录 threshold、原有效候选数、候选截断数、NMS保留及结果上限截断数、clip移除数，明确结果有界。
IoU及坐标算术使用 float64，禁止输入 float32 几何计算溢出或依赖不稳定 NMS tie-breaking。

preview 是校正后 RGB 等比例缩小，最大边1280、不放大；同样整数最近舍入与 BILINEAR，PNG<=8MiB。PNG固定RGB、compress_level=6、optimize=False，
重新创建无info的RGB对象，不传 pnginfo/exif/icc_profile；自有探针PNG同一编码参数。
不绘制框，前端按校正后的原图尺寸绘制。preview 的输出像素尺寸与hash独立记录。

## 5. 真执行和错误

PT：复用 training_runtime prepare_environment / initialize 的固定 safe globals、weights_only=True、
allowlist、CPU/版本检查；只加载复制出的可信 PT。校验 DetectionModel、类顺序、finalized checkpoint、
全部参数有限、唯一标准 Detect head；设 export=True/format=onnx/dynamic=False 后直接执行一次 raw。
不调用高层 predict、不下载。每个子进程 initialize 仅一次。
ORT：import 前关闭遥测；核验已有严格 ONNX graph、external data/custom op/IO/shape，checker 真运行；
CPUExecutionProvider、intra2/inter1、sequential、ORT_DISABLE_ALL；disable_fallback 且实际 provider 必须唯一 CPU。
只执行所选复制 ONNX；不能失败后 PT。固定 NumPy2.5.4，ORT1.31.1，ONNX1.23.2；沿用完整 joint lock。

记录实际 backend/provider、精确相关版本、线程、模型/image/tensor/raw hash、类别、预处理和阈值；
monotonic 计时分 decode/preprocess/load/infer/postprocess/total，单位毫秒、有限非负，warmup_runs=0。
未测值为 null，不伪填0；单图耗时不是基准性能。

沿用 E 的固定 runner exit code → 脱敏错误协议，不用 stdout 正则猜原因。新增 I 独立类别：
IMAGE_DECODE_FAILED、IMAGE_FORMAT_MISMATCH、IMAGE_MULTIFRAME、IMAGE_PIXEL_LIMIT、IMAGE_MODE_UNSUPPORTED、
PT_LOAD_REJECTED、ORT_DEPENDENCY_MISSING、ORT_MODEL_INVALID、ORT_PROVIDER_MISMATCH、ORT_EXECUTION_FAILED、
INFERENCE_OUTPUT_INVALID；安全策略失败保持 INFERENCE_POLICY_FAILED，存储/容量/输入变化/runtime变化及取消/恢复
沿用已有语义。原生异常不公开任意文本；完整性错误不得变成成功空检测。有限 exit code 映射在实现时一处定义并测试。
上传规范错误 400/413/415/503，提交 422 或 409 INFERENCE_INPUT_UNAVAILABLE/MODEL_BACKEND_MISMATCH/
INFERENCE_SETUP_REQUIRED/IDEMPOTENCY_CONFLICT；归属错404、禁用会话401、CSRF403、归档409。
结果历史发布束损坏 409 ARTIFACT_UNAVAILABLE；非结果 kind / 他人 ID 为404。

## 6. 完整束发布

run 位于既有 `jobs/{job_id}/runs/{run_id}`，独立 image/source copy、input/evidence；bundle **只有**
result.json、metadata.json、preview.png。JSON各<=1MiB，preview<=8MiB，detections<=300，模型<=128MiB。
元数据含 result/preview 指纹和 provenance；result 不含元数据自hash，避免循环绑定。
所有写入 exclusive/atomic + fsync；超限失败而非截断。evidence 严格绑定 job/run/frozen digest 和三个成员。
整树 drain 完整、guardian 退出、所有来源和束都匹配后，intent → rename 至
`inferences/{job_id}/{run_id}` → 复验 → 短事务插入 passed inference_result（parent_id=所选模型ID）并 CAS succeeded。
取消赢 CAS 不登记成功；缺 receipt 停领；不自动重跑、不用孤儿恢复成功；不修改输入 Artifact。
归档允许旧任务完成/取消/历史，不额外制造隐式取消政策。

## 7. 新 I 能力 probe（本次不执行）

E rgb-fixed-v1 raw 张量探针**不能**授权 detection-image-v1。新增独立 inference-capability.json v1，
绑定完整当前 I 代码、共同算法源及协议、解释器/二进制、joint lock、已安装发行 RECORD、精确依赖版本。
新增 I 文件、共享 schemas/worker/task_process/上传 helper 等都纳入 identity；旧记录自然失效。
读取 capabilities 只做轻量身份/严格记录核验，不 import ML、不自动启动 probe。

操作员显式 CLI `python -m app.inference_probe --onnx-artifact-id <UUID>`，只接受 DB 中同项目已成功 E 的
ONNX及其 provenance.parent_artifact_id；重验 E 完整束及父 PT可信源。不接受路径/URL/其他项目父模型。
可验证历史成功 E 的完整产物，不要求旧 E capability 在新 I 代码下仍 available；历史来源严格核验与
当前 I runtime identity 分开，避免无意义的 E 探针重跑依赖。
probe 创建无用户图片的自有 deterministic PNG：257×193 RGB，每像素
`R=(3*x+y)%256, G=(x+5*y)%256, B=(7*x+11*y)%256`，无元数据，固定 PNG 编码选项；
将协议/生成源码 hash、PNG bytes hash、原像素和张量 hash纳入证据。固定 confidence=.25、iou=.45。

父进程持有**同一 worker.lock**覆盖来源冻结、两个子阶段和最终记录；本次尝试在核验来源/启动前原子写
available=false，任何失败不得遗留旧true；先 recover_probe + recover，
任一退出不明即停。PT和ONNX分两个**顺序的全新 guardian/task_process 子进程**，各用唯一 run_id；
每阶段启动前写已有 training-probe-active.json 歧义记录，GO 后运行同一生产图像核心/适配器，
有完整 drain/started/logs_complete/exit0 且guardian确实退出后才允许下阶段。不能自行嵌套 Popen、
并发 probe 或在同一子进程重复 torch.set_num_interop_threads。不新增测试开关或绕过共享恢复入口。

两阶段均以同一冻结来源对、相同合成 PNG、协议和 runtime/code 绑定执行；子证据保存完整真实文档/raw指纹，
父进程在每次退出后重验源/copy、输出/receipt；末尾再次核验 runtime/source。只有两个模式都真通过才写
available=true，分别存 PT/ONNX proof 与 guardian/run/receipt 绑定；否则保持 false。PT capability 不会由
单独 PT 成功提前开放。保留既有 API features pt_inference 和 onnx_inference 均依赖此双模式新记录。
完整 probe 记录严格、有界；仅已验证相同合成输入/预处理与模式、且各自 backend/provider 正确才接受。
不要求探针返回非空框；空框不影响真正执行的证明。旧训练/E capability 不作为 I 成功证据。

每个私有 probe run 保留 `raw.f32le`，固定 `[1,4+nc,8400]` little-endian FP32 C-order，
精确大小 `(4+nc)*8400*4`，nc<=1000 时最多33,734,400字节。严格probe proof绑定其size/hash、
backend、源模型/合成图片/张量摘要、job/run和当前runtime/code；普通 infer 不发布raw。父进程在
两阶段整树退出后从同一核验描述符有界流式读取，以标准库 struct/array 按元素比较下面的raw容差，
struct 转 Python float 进行float64算术，完整校验元素数、截断、多余字节、非有限值及同描述符hash。
不导入NumPy、不把数组塞进1MiB JSON或最终三文件bundle、不拿hash相同代替容差。最终能力记录保存
摘要、元素计数、max_absolute_error/max_tolerance_ratio和匹配结论，不嵌入raw。两阶段分别的真实detections再用
冻结双射规则比较，原始raw仅保留私有探针目录，不进入源码、用户发布束、公开报告或上传。

原生验收额外对同图 PT/ONNX raw 使用预冻结 `abs(ORT-PT)<=1e-4+1e-4*abs(PT)`，
检测集数量相等且存在同类一对一双射，每对 IoU>=.99、score绝对差<=.001、四个xyxy坐标各绝对差<=.5px；
两空集合通过，一个为空另一个非空或数量不同失败。按PT输出顺序和ONNX输出顺序作确定性增广路二分图匹配，
只有满足全部阈值才建边，必须覆盖双方，不能用近邻贪心漏掉可行双射。检测级容差容纳从raw到原图的缩放，
但不替代全raw逐元素严格容差。不事后放宽，近阈值差异需报告失败并审查。
纯逻辑非空/空检测测试与原生证据分开；探针只是工程可执行性，不是精度实验。

## 8. 兼容、回退和验证

既有表/迁移不变；I旧占位没有成功业务记录，若发现真实历史 I 数据先停止收紧并提兼容方案。
E/PT原有 metadata 不改；严格 I 分支与可空 JobPublic.inference 是增量，TS同步生成。
仅提取最小上传策略及 ONNX验证 helper，不顺带重构平台；共享变化须跑 T030/T040/T050/E 回归。
回退先禁用新 I 提交/能力，确认活动进程退出，保留输入和历史结果；旧Worker不得领取 infer。
不能删库、清理孤儿来伪恢复，不需 Alembic downgrade；历史读取按已保存协议而非当前探针新鲜度校验。

实施顺序：本 ADR 独立设计审查 → 严格 DTO/共同核心/上传与来源接口契约检查点 → 后端服务/runner/发布/
读取/能力/Worker整合 → 轻量独立复核 → 精确 SHA 申请受控原生/HTTP/浏览器验证。P始终留待 I 验收。
前端由独立 worktree 接入，契约生成检查点立即通告。

必要轻量/普通受管进程矩阵：严格类型/extra/交叉绑定；无ML API import；上传真实body/重复part/坏头/
空文件/MIME/断线/磁盘错误/前后鉴权竞态；跨项目/归档/重放/重试；图像decode模式/EXIF八方向/alpha/多帧/
坏图/像素界限；letterbox奇数边/逆变换/稳定tie/class-aware/score和IoU等阈值/上限/空框；模型与输入
metadata/hash/intent/copy grow-truncate/链接替换；缺产物/extra成员/容量；GO前后取消/完成竞态/Worker丢失/
缺receipt/rename窗口/stale-run；历史完整束/同描述符下载/断线释放；新probe共享互斥/恢复/旧绑定失效。
原生 PT/ORT/缺ORT/坏图/错provider、双模式真probe、真实HTTP/浏览器、Windows ML 均另记 NOT_RUN。

停止条件：设计审查未放行、权限不足、协议无法严格表达、真实运行缺隔离或精确SHA授权、历史数据兼容未知、
依赖/来源不完整。只停受影响工作，报告具体动作/原因，不下载、重训、伪造probe或越过P闸门。
