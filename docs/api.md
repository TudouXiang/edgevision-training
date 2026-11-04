# HTTP 契约 V0.4 · T040 候选

唯一机器可读来源：backend/app/schemas.py 与 backend/app/main.py 生成 FastAPI OpenAPI，生成入口见 scripts/export_contract.py。本文件解释语义。T010/T020 已 accepted；T030 候选复用 `0002_foundation`，实现受限 ZIP staging、Dataset 版本记录、owner-aware 查询和 ready-only 有界预览，T040 以 0003_worker 接入真实异步校验，当前待最终验收。生成契约与前端类型已同步，见 ADR 0008 与 `docs/evidence/T030-report.md`。

根 /api/v1，时间带时区 UTC ISO 8601、UUID、snake_case。成功直接返回 DTO；列表为 items、total、page、page_size，page 从 1 起且 page_size 1–100。增量日志/指标返回 items、next_cursor、eof、job_state，limit 1–500，游标绑定单 Job 且单调；轮询间隔约 2 秒，失败退避，终态最后拉取一次。V1 不使用 SSE。

| 路径 | 输入/成功 DTO | 状态 |
| --- | --- | --- |
| GET /health/live、/health/ready、/capabilities | LiveResponse、ReadyResponse、CapabilitiesResponse；能力每项有 available、reason_code、reason、detected_version | 健康/就绪接口，安装不等于实测 |
| POST /auth/login、/logout、/change-password；GET /auth/me | LoginRequest、ChangePasswordRequest、UserPublic，会话 Cookie；登出/改密 204 | T020 已实现，accepted（Linux CI） |
| GET/POST /projects、GET/PATCH /projects/{id}、POST /projects/{id}/archive | ProjectCreate/Update/Public、Page[ProjectPublic] | T020 已实现，accepted（Linux CI） |
| GET/POST /projects/{id}/datasets、GET /datasets/{id} | Page[DatasetPublic]；multipart 的单一 `file` ZIP，成功登记真实 pending Dataset | T030 核心已实现、accepted（Linux CI）；完整校验不在 HTTP 请求执行 |
| POST /datasets/{id}/check | Idempotency-Key，成功语义为 202 JobAccepted | T040 已实现；幂等同键返回原 Job 的当前 state，不仅 queued |
| GET /datasets/{id}/samples、GET /datasets/{id}/samples/{sample_id}/image | Page[DatasetSamplePublic]；opaque sample ID 的鉴权图片流 | T030 核心已验收；仅 ready 且 manifest 合法时可读，pending/invalid 拒绝 |
| GET/POST /projects/{id}/jobs、GET /jobs/{id}、POST /jobs/{id}/cancel | Page[JobPublic]、判别式 JobCreate(kind,params)、JobAccepted、JobPublic | T040 已实现列表/详情/取消和 dataset_check 创建；其他 kind 501 |
| GET /jobs/{id}/logs、/metrics | Incremental[JobLog/Metric]；cursor、limit | T040 已实现有界查询；dataset_check 没有虚构 metrics |
| GET /projects/{id}/artifacts、GET /artifacts/{id}、/download | Page[ArtifactPublic]、ArtifactPublic、鉴权文件流 | T040 已实现真实 dataset_report 列表/详情/鉴权哈希校验下载；其他下载格式仍按后续任务实现 |
| POST /projects/{id}/images、GET /inferences/{id} | 单图 multipart 上传返回图片 ArtifactPublic；结果为 InferenceResult | T060；目前 501，无图片解析 |
| GET/POST /admin/users、PATCH /admin/users/{id}、GET /admin/projects | UserCreate/Update/Public、项目分页 | T020 已实现，accepted（Linux CI）；最后一个启用管理员不能被禁用 |
| GET /admin/jobs | Page[JobPublic] | T070；管理员身份校验后仍返回 501 |

JobCreate.kind 只接受 dataset_check/train/export_onnx/infer/package 且 params 与 kind 配对，不透传任意键。训练限预置 yolo11n.pt、epochs 1–100、batch 1–16、imgsz 320/640、cpu 或 cuda:0、seed 0–4294967295、学习率 1e-6–0.1；设备的 DTO 可解析不代表已验证可执行。导出限 batch=1/FP32/640；opset 与后处理须在目标版本真实烟测后锁定，当前不能接受任意 opset。推理 DTO 只可引用由平台登记的图片 artifact ID，后续需受限单图上传入口，尚未实现。

创建 Job 和异步数据校验需要 Idempotency-Key，同用户+操作+键相同参数返回原任务，不同参数 409。所有资源服务端核对会话、角色、owner 与归档：他人对象返回 404；归档项目的新上传/新任务入口返回 409。数据集上传读取 body 前鉴权，流式 staging 后在短写事务再次鉴权；成功只返回 pending Dataset，不代表校验完成。Job 提交/同键重放为 202 JobAccepted，state 反映原任务当前状态；新任务 queued 不代表完成。未知路径 404、无效字段 422；错误固定为 error.code、error.message、error.request_id、error.details，422 不回显敏感输入。数据库未迁移使身份/业务接口返回 503。

登录及所有修改请求拒绝缺失、`null` 或不在明确允许列表中的 Origin。服务端只保存随机 session/CSRF 令牌的 SHA-256，浏览器收到 HttpOnly `edgevision_session` 与可供同源前端读取的 `edgevision_csrf`；修改请求同时验证 Origin、Cookie 和 `X-CSRF-Token`。改密撤销该用户所有旧会话并签发一组新令牌；登出、过期、禁用和撤销立即在后端查询时生效。密码采用 Argon2id。开发 Origin 与 HTTPS/Secure Cookie 配置见 README 和 ADR 0007。

旧 SSE 路径和 /training-jobs 等历史路径不再属于本候选契约；理由与迁移见 ADR 0005。旧源码可用 Git 历史回溯，不向用户隐式返回模拟成功。T030 multipart 已真实受限落盘；异步 check 已接入固定 Worker；训练、模型和部署仍不可用，pending 不能训练或预览。


T040 DatasetPublic 新增可空 validation_job_id/report_artifact_id；当前报告指针不指向上一次尝试。同一 Dataset 有 queued/running/cancelling 时不同键复用该活动 Job；ready 不能重新校验，上传新版本才能变更。取消/中断/基础设施失败恢复 pending，真实内容错误为 invalid + DATASET_INVALID 报告。归档拒绝全新提交，不影响已有任务完成/取消；同键重放仍可读取原任务。

日志游标是 v1:job-uuid:log-or-metric:seq，绑定任务和流，越界/畸形为 422 CURSOR_INVALID；每次最多 64 KiB（且不超过 limit 项），高水位内单调。终态 eof 仅在日志读完时为 true，客户端必须最终读取。捕获最多 512 KiB/2000 项加一条截断提示，超限仍 drain 子进程输出；用户界面最多保留 500 行。只有固定脱敏 adapter 日志可见，任意 stdout/traceback 被替换。报告最大 16 MiB，下载返回已核对 size/SHA 的同一字节，不暴露存储路径。
