# HTTP 契约 V0.1 · T010 候选

唯一机器可读来源：backend/app/schemas.py 与 backend/app/main.py 生成 FastAPI OpenAPI，生成入口见 scripts/export_contract.py。本文件解释语义；本执行容器无法导入 FastAPI，contracts/openapi.json 与 contracts/generated/openapi.ts 尚未生成，A03 仍未通过。旧 contracts/api.ts 只为已有健康页面保留临时类型，后续须替换。

根 /api/v1，时间带时区 UTC ISO 8601、UUID、snake_case。成功直接返回 DTO；列表为 items、total、page、page_size，page 从 1 起且 page_size 1–100。增量日志/指标返回 items、next_cursor、eof、job_state，limit 1–500，游标绑定单 Job 且单调；轮询间隔约 2 秒，失败退避，终态最后拉取一次。V1 不使用 SSE。

| 路径 | 输入/成功 DTO | 状态 |
| --- | --- | --- |
| GET /health/live、/health/ready、/capabilities | LiveResponse、ReadyResponse、CapabilitiesResponse；能力每项有 available、reason_code、reason、detected_version | 健康/就绪接口，安装不等于实测 |
| POST /auth/login、/logout、/change-password；GET /auth/me | LoginRequest、ChangePasswordRequest、UserPublic，会话 Cookie；登出/改密 204 | T020；目前 501 |
| GET/POST /projects、GET/PATCH /projects/{id}、POST /projects/{id}/archive | ProjectCreate/Update/Public、Page[ProjectPublic] | T020；目前 501 |
| GET/POST /projects/{id}/datasets、GET /datasets/{id}、POST /datasets/{id}/check、GET /datasets/{id}/samples | 上传 multipart/form-data，字段 file 为单一 ZIP，成功 DatasetPublic；校验 JobAccepted，样本分页 | T030/T040；目前 501，multipart 只描述于 OpenAPI，尚无流式解析 |
| GET/POST /projects/{id}/jobs、GET /jobs/{id}、POST /jobs/{id}/cancel | Page[JobPublic]、判别式 JobCreate(kind,params)、JobAccepted、JobPublic | T040/T050；目前 501 |
| GET /jobs/{id}/logs、/metrics | Incremental[JobLog/Metric]；cursor、limit | T040/T050；目前 501 |
| GET /projects/{id}/artifacts、GET /artifacts/{id}、/download | Page[ArtifactPublic]、ArtifactPublic、鉴权文件流 | T050/T060；目前 501 |
| POST /projects/{id}/images、GET /inferences/{id} | 单图 multipart 上传返回图片 ArtifactPublic；结果为 InferenceResult | T060；目前 501，无图片解析 |
| GET/POST /admin/users、PATCH /admin/users/{id}、GET /admin/projects、/jobs | UserCreate/Update/Public、分页 | T020/T070；目前 501 |

JobCreate.kind 只接受 dataset_check/train/export_onnx/infer/package 且 params 与 kind 配对，不透传任意键。训练限预置 yolo11n.pt、epochs 1–100、batch 1–16、imgsz 320/640、cpu 或 cuda:0、seed 0–4294967295、学习率 1e-6–0.1；设备的 DTO 可解析不代表已验证可执行。导出限 batch=1/FP32/640；opset 与后处理须在目标版本真实烟测后锁定，当前不能接受任意 opset。推理 DTO 只可引用由平台登记的图片 artifact ID，后续需受限单图上传入口，尚未实现。

创建 Job 和异步数据校验需要 Idempotency-Key，同用户+操作+键相同参数返回原任务，不同参数 409。业务成功仍需会话、CSRF 与项目 owner 鉴权；当前仅占位 501，不把路由存在当权限已实现。成功 Job 创建为 202 JobAccepted，state 为 queued，不能当任务完成。未知路径 404、无效字段 422；错误固定为 error.code、error.message、error.request_id、error.details，422 不回显敏感输入。未实现返回 501 NOT_IMPLEMENTED；存储/数据库缺失使 ready 返回 503。

旧 SSE 路径和 /training-jobs 等历史路径不再属于本候选契约；理由与迁移见 ADR 0005。旧源码可用 Git 历史回溯，不向用户隐式返回模拟成功。当前 multipart 的文档声明不代表可传输，真实请求仍由占位处理器 501 拒绝。
