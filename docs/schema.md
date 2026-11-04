# SQLite 数据库结构 V1

由 Alembic `0001_initial` 建立原骨架，再由 `0002_foundation` 兼容迁移到当前契约，不编辑已有第一版。正式运行不以 ORM `create_all` 隐式建表。所有时间 UTC 带时区字符串，由应用层生成；操作事务短。应用连接启用外键 `ON`、WAL 与 busy_timeout，迁移的隔离连接为重建表暂关外键且在结束前执行 `foreign_key_check`。版本由 Alembic 管理，目标为 `0003_worker`；0001/0002 保持原样，0003 仅添加执行证据与 validation_job_id。隔离迁移、旧版样本升级与回退守卫见 T040 报告。

| 表 | 关键字段和约束 | 作用 |
| --- | --- | --- |
| `users` | id PK、username UNIQUE、password_hash、role CHECK(user/admin)、is_active、created_at | T020 使用 Argon2id；无默认用户，首个管理员由显式交互 CLI 创建 |
| `sessions` | id PK、user_id FK、token_hash UNIQUE、csrf_hash、expires_at、created_at、revoked_at | 只存会话令牌哈希，登出及禁用后失效 |
| `projects` | id PK、owner_id FK、name、description、task_type CHECK(detection)、status CHECK(active/archived)、archived_at nullable、created_at/updated_at | 所有权边界；owner_id+updated_at 索引 |
| `datasets` | id PK、project_id FK、parent_id FK nullable、version INTEGER、name、archive_key、snapshot_key、sha256、size_bytes、status CHECK(pending/validating/ready/invalid)、report_key nullable、validation_job_id FK jobs nullable、counts_json、classes_json、manifest_json、created_at；UNIQUE(project_id,name,version) | 每次导入/修订创建新行，ready 快照不就地覆盖；0002 映射旧 uploaded/valid |
| `jobs` | id PK、project_id FK、owner_id FK、kind CHECK(dataset_check/train/export_onnx/infer/package)、status CHECK(queued/running/cancelling/cancelled/succeeded/failed/interrupted)、payload_json/params_schema_version/input_snapshot_json/environment_json/code_version、retry_of_id、worker_pid/child_pid/child_pgid、run_id/worker_instance/host_boot_id、cancel_requested_at、process_identity_json/launch_phase/publication_json、error_code/error_message、created_at/started_at/finished_at/heartbeat_at；status+created_at 索引 | 一个 Job 表覆盖所有异步任务；旧 validate 映射 dataset_check；owner_id 对应 DTO created_by |
| `job_events` | job_id FK、seq INTEGER、kind CHECK(status/log/metric)、payload_json、created_at；PK(job_id,seq) | 续传日志与状态的持久游标 |
| `metrics` | id PK、job_id FK、epoch、name、value REAL、created_at；UNIQUE(job_id,epoch,name) | 可比较训练曲线，指标来自真实日志 |
| `artifacts` | id PK、project_id FK、job_id FK nullable、parent_id FK nullable、kind CHECK(dataset_report/pt_best/pt_last/onnx/inference_input/inference_result/deployment_zip)、format、storage_key UNIQUE、sha256、size_bytes、validation_status CHECK(unverified/passed/failed)、metadata_schema_version、metadata_json、created_at/validated_at | 文件索引、来源链、验证状态及哈希；DTO 名为 validation_state |
| `idempotency_keys` | owner_id FK、request_key、method、path、body_sha256、job_id FK、created_at；UNIQUE(owner_id,request_key,method,path) | 避免重试造成重复重任务 |

对象关系：`users 1─* projects`、`projects 1─* datasets/jobs/artifacts`、`jobs 1─* events/metrics/artifacts`。数据集 snapshot ID 保存在训练 job 的 payload 内，模型产物 metadata 内也保留它；删除/归档前检查引用关系，物理文件清理由明确管理任务完成，不用 SQLite 触发器直接删文件。

约束不变量：`succeeded` 只能在产物哈希验证后写入（`dataset_check` 等非模型任务须有真实报告）；终态不变；`started_at`/`finished_at` 跟随转换；单重任务串行依赖 Worker 单实例锁+事务领取，不靠表中假想的 DB 全局锁。jobs.owner_id 记录真实提交 actor，对外为 created_by；管理员代项目所有者提交时两者可以不同。资源可见/取消权限只沿 Project.owner_id 校验并允许管理员，不接受请求体 owner_id。恢复时不确定进程身份则停止领取，不能仅依赖 PID 判死活。

T020 复用既有表，不新增迁移。禁用用户与改密在同一写事务撤销会话；写操作在同一 `BEGIN IMMEDIATE` 事务中重新核对会话、启用状态和角色，避免鉴权与写入之间的禁用/撤销竞态。

数据库存大文件路径的相对键，不存绝对路径或模型二进制；metadata_json 带 `schema_version`，字段格式见 `model-metadata.md`。


0003 回退必须停止 API/Worker，确认没有 queued/running/cancelling Job 和 validating Dataset，否则迁移拒绝。`validation_job_id` 是完成/恢复时的 stale-run 防护；终态不复活。取消、中断和基础设施失败恢复匹配 Dataset 为 pending；内容拒绝才 invalid。每次新校验清空当前 report_key，历史报告 Artifact 和原 Job 不删除。发布成功事务同时更新 Dataset、Artifact 和 Job CAS/status event。
