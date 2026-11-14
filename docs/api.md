# HTTP 契约 · T060 I 源码候选

唯一机器可读来源：backend/app/schemas.py 与 backend/app/main.py 生成的 FastAPI OpenAPI，生成入口见 scripts/export_contract.py。本文件解释当前语义。T010–T050 已按各自证据限定验收；T060 E 限定工程accepted，I源码已完成独立审查但真实模型/浏览器未验收，P仍501。当前数据库目标为0003_worker；阶段及限制见[项目状态](status.md)、[验收矩阵](acceptance.md)。

根 /api/v1，时间带时区 UTC ISO 8601、UUID、snake_case。成功直接返回 DTO；列表为 items、total、page、page_size，page 从 1 起且 page_size 1–100。增量日志/指标返回 items、next_cursor、eof、job_state，limit 1–500，游标绑定单 Job 且单调；轮询间隔约 2 秒，失败退避，终态最后拉取一次。V1 不使用 SSE。

| 路径 | 输入/成功 DTO | 状态 |
| --- | --- | --- |
| GET /health/live、/health/ready、/capabilities | LiveResponse、ReadyResponse、CapabilitiesResponse；能力每项有 available、reason_code、reason、detected_version | 健康/就绪接口，安装不等于实测 |
| POST /auth/login、/logout、/change-password；GET /auth/me | LoginRequest、ChangePasswordRequest、UserPublic，会话 Cookie；登出/改密 204 | T020 已实现，accepted（Linux CI） |
| GET/POST /projects、GET/PATCH /projects/{id}、POST /projects/{id}/archive | ProjectCreate/Update/Public、Page[ProjectPublic] | T020 已实现，accepted（Linux CI） |
| GET/POST /projects/{id}/datasets、GET /datasets/{id} | Page[DatasetPublic]；multipart 的单一 `file` ZIP，成功登记真实 pending Dataset | T030 核心已实现、accepted（Linux CI）；完整校验不在 HTTP 请求执行 |
| POST /datasets/{id}/check | Idempotency-Key，成功语义为 202 JobAccepted | T040 已实现；幂等同键返回原 Job 的当前 state，不仅 queued |
| GET /datasets/{id}/samples、GET /datasets/{id}/samples/{sample_id}/image | Page[DatasetSamplePublic]；opaque sample ID 的鉴权图片流 | T030 核心已验收；仅 ready 且 manifest 合法时可读，pending/invalid 拒绝 |
| GET/POST /projects/{id}/jobs、GET /jobs/{id}、POST /jobs/{id}/cancel | Page[JobPublic]、判别式 JobCreate(kind,params)、JobAccepted、JobPublic | 已实现列表/详情/取消及dataset_check/train/export_onnx/infer创建；模型执行要求当前受管probe，package仍501 |
| GET /jobs/{id}/logs、/metrics | Incremental[JobLog/Metric]；cursor、limit | T040 已实现有界查询；dataset_check 没有虚构 metrics |
| GET /projects/{id}/artifacts、GET /artifacts/{id}、/download | Page[ArtifactPublic]、ArtifactPublic、鉴权文件流 | 已实现dataset_report/PT/ONNX及I结果列表、详情与受限下载；unverified原图片不提供下载 |
| POST /projects/{id}/images、GET /inferences/{id}、GET /inferences/{id}/image | 单图multipart返回InferenceInputArtifactPublic；结果为InferenceResult与鉴权净化PNG | I源码已实现；上传只存unverified字节，解码在受管子进程，真实模型验收未执行 |
| GET/POST /admin/users、PATCH /admin/users/{id}、GET /admin/projects | UserCreate/Update/Public、项目分页 | T020 已实现，accepted（Linux CI）；最后一个启用管理员不能被禁用 |
| GET /admin/jobs | Page[JobPublic] | T070；管理员身份校验后仍返回 501 |

JobCreate.kind 只接受 dataset_check/train/export_onnx/infer/package 且 params 与 kind 配对，不透传任意键。训练限预置 yolo11n.pt、epochs 1–100、batch 1–16、imgsz 320/640、cpu 或 cuda:0、seed 0–4294967295、学习率 1e-6–0.1；设备的 DTO 可解析不代表已验证可执行。导出限 batch=1/FP32/640；opset 与后处理须在目标版本真实烟测后锁定，当前不能接受任意 opset。推理DTO只可引用受限单图上传登记的图片artifact ID与本项目可信模型；真实执行须当前代码绑定的I双模式probe。

创建 Job 和异步数据校验需要 Idempotency-Key，同用户+操作+键相同参数返回原任务，不同参数 409。所有资源服务端核对会话、角色、owner 与归档：他人对象返回 404；归档项目的新上传/新任务入口返回 409。数据集上传读取 body 前鉴权，流式 staging 后在短写事务再次鉴权；成功只返回 pending Dataset，不代表校验完成。Job 提交/同键重放为 202 JobAccepted，state 反映原任务当前状态；新任务 queued 不代表完成。未知路径 404、无效字段 422；错误固定为 error.code、error.message、error.request_id、error.details，422 不回显敏感输入。数据库未迁移使身份/业务接口返回 503。

登录及所有修改请求拒绝缺失、`null` 或不在明确允许列表中的 Origin。服务端只保存随机 session/CSRF 令牌的 SHA-256，浏览器收到 HttpOnly `edgevision_session` 与可供同源前端读取的 `edgevision_csrf`；修改请求同时验证 Origin、Cookie 和 `X-CSRF-Token`。改密撤销该用户所有旧会话并签发一组新令牌；登出、过期、禁用和撤销立即在后端查询时生效。密码采用 Argon2id。开发 Origin 与 HTTPS/Secure Cookie 配置见 README 和 ADR 0007。

旧 SSE 路径和 /training-jobs 等历史路径不再属于本候选契约；理由与迁移见 ADR 0005。旧源码可用 Git 历史回溯，不向用户隐式返回模拟成功。T030 multipart 已真实受限落盘；异步 check 已接入固定 Worker；训练/导出/推理按各自当前probe放行，部署仍未实现；pending数据集不能训练或预览。


T040 DatasetPublic 新增可空 validation_job_id/report_artifact_id；当前报告指针不指向上一次尝试。同一 Dataset 有 queued/running/cancelling 时不同键复用该活动 Job；ready 不能重新校验，上传新版本才能变更。取消/中断/基础设施失败恢复 pending，真实内容错误为 invalid + DATASET_INVALID 报告。归档拒绝全新提交，不影响已有任务完成/取消；同键重放仍可读取原任务。

日志游标是 v1:job-uuid:log-or-metric:seq，绑定任务和流，越界/畸形为 422 CURSOR_INVALID；每次最多 64 KiB（且不超过 limit 项），高水位内单调。终态 eof 仅在日志读完时为 true，客户端必须最终读取。捕获最多 512 KiB/2000 项加一条截断提示，超限仍 drain 子进程输出；用户界面最多保留 500 行。只有固定脱敏 adapter 日志可见，任意 stdout/traceback 被替换。报告最大 16 MiB，下载返回已核对 size/SHA 的同一字节，不暴露存储路径。

## T050 训练增量（固定Linux CPU范围已限定验收）

POST `/projects/{id}/jobs` 放开 train，额外可空 source_job_id 只允许同项目终态 train，用于新任务来源而非恢复。
提交冻结 ready Dataset 的完整报告/清单、资产和环境指纹；CPU 探针缺失或过期返回 TRAINING_SETUP_REQUIRED，
CUDA 返回 DEVICE_UNAVAILABLE，未 ready 返回 DATASET_NOT_READY。公共 Job.training 为生成的 TrainingProvenance，
只含白名单资源 ID、摘要、参数和类别；PT metadata 使用 TrainingArtifactMetadata/TrainingRuntime。
日志仍单独有界；metric journal 独立配额，单调 epoch/seq、有限值和名称白名单。终态指标也必须读取至 eof。
best/last 下载根据同一个已核验文件描述符流式读取，最大 128 MiB，断线关闭资源。

## T060 E：固定 ONNX 导出（限定工程验收）

76af的真实隔离结果与后续错误协议增量复核严格分开，详见[E逐项验收](evidence/T060-export-acceptance-2026-11-05.md)；这不证明新I原生执行。

`POST /projects/{id}/jobs` 的 `kind=export_onnx` 已接入同一队列；参数仅为
`model_artifact_id`、`imgsz=640`、`batch=1`、`precision=fp32`。未知参数、布尔维度、动态尺寸、简化和量化均拒绝。
来源必须同项目、`pt_best/pt_last`、`passed`，且所属训练 Job 为 `succeeded`；原训练发布 intent、原 metadata 文件、源 PT、完整冻结数据及报告均复核。
需要当前固定联合环境的受管导出探针，否则返回 `409 DELIVERY_SETUP_REQUIRED`，不因安装 ONNX 就宣称可用。
其他来源完整性问题返回 `409 EXPORT_INPUT_UNAVAILABLE`。幂等键同请求返回既有 Job，冲突为 409；已有幂等任务可在项目归档后读取，不新建工作。

`JobPublic.export` 提供不含服务器路径的冻结源模型 ID、源训练 Job、源摘要、参数与代码/运行绑定。
`ArtifactPublic` 是按 `kind` 判别的严格联合类型。ONNX 分支必须为 `OnnxArtifactMetadata`，不能落入通用字典分支。
`GET /artifacts/{id}/download` 对 ONNX 校验成功任务、发布 intent、metadata/validation 文件和完整绑定，并校验模型文件后从同一描述符有界返回。
跨用户与跨项目资源仍 404；损坏产物返回 `409 ARTIFACT_UNAVAILABLE`。下载历史模型不要求当前代码探针仍有效。

`/capabilities.features.onnx_export` 取自独立 `delivery-capability.json` 的当前绑定；`models` 表示已有模型列表/下载实现，不表示 ML 环境可用。
`infer` 源码按下一节实现，只有当前I双模式probe有效才开放对应能力；`package`仍501。E的旧真实证据不替代新I验收。

## T060 I 图片接口增量

本节描述已实现的候选源码，不代表真实模型验收通过。精确schema以生成OpenAPI/TS为准。

- POST /api/v1/projects/{project_id}/images：single file multipart，受限JPEG/PNG原bytes，201为
  InferenceInputArtifactPublic；validation_state=unverified、job_id=null。没有上传幂等保证。
- POST /api/v1/projects/{project_id}/jobs：kind=infer，params含model_artifact_id、image_artifact_id、
  backend=pt|onnx、严格有限confidence/iou（默认.25/.45）；可空source_job_id为同项目终态infer。
  必须Idempotency-Key；202只是排队。当前无有效I probe时409 INFERENCE_SETUP_REQUIRED。
- JobPublic.inference为脱敏来源/参数/协议/runtime/code摘要；既有Job/Artifact列表用于刷新历史。
- GET /api/v1/inferences/{result_artifact_id}：严格InferenceResult，包括actual backend/provider、
  EXIF校正后原图尺寸及xyxy、检测/预处理/计时/preview摘要和鉴权image_url。
- GET /api/v1/inferences/{result_artifact_id}/image：image/png，无原EXIF/ICC/注释，最大边1280。
- GET /api/v1/artifacts/{result_artifact_id}/download：application/json结果；未验证原输入下载409。

他人/非结果ID为404；损坏完整发布束或读取竞态为409 ARTIFACT_UNAVAILABLE。上传400/413/415/503、
参数422、模型后端错配409、会话401/CSRF403/归档409均使用规范error envelope。P接口仍501。
