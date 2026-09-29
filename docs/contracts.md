# 核心契约 V0.1

状态：用户启动包的设计约束。T010 的候选 Pydantic DTO、`0002_foundation` 迁移及生成 OpenAPI/TS 已在 Windows 隔离环境运行；A01–A04 为待独立审查的 PASS 候选，见 `docs/evidence/T010-windows-2026-09-28.md`。此文件不替代生成后的 OpenAPI；内部字段允许补充，外部语义变更需经 ADR 与审查。

## 1. 全局约定

资源 ID 使用 UUID 字符串；服务端时间使用 UTC，HTTP 用带时区 ISO 8601；Python/HTTP 字段使用 snake_case；缺失值用 null，不用 -1 或虚构的 0 代替未知指标。用户名与资源名称的长度/唯一性约束在 DTO 与数据库统一。

所有受保护资源通过 Project 所有者追溯授权；管理员可跨项目操作，普通用户不能仅靠猜 UUID 访问别人的资源。Dataset/Job/Artifact 必须与同一 Project 的引用保持一致，创建和读取两端均校验。禁止客户端自填 owner_id 获得权限。

## 2. 核心记录

|记录|关键内容与约束|
|---|---|
|User|id、username、password_hash、role(user/admin)、is_active、created_at；不开自助注册|
|Session|id、user_id、token_hash、expires_at、revoked_at；原始令牌不落库，禁用用户或改密时撤销旧会话|
|Project|id、owner_id、name、description、archived_at；归档保留历史，归档项目不接受新任务|
|Dataset|id、project_id、name、state、storage_key、内容清单摘要、类别顺序、split/样本统计、created_at；ready 后内容不可原地替换|
|Job|id、project_id、created_by、kind、state、params_schema_version、params_snapshot、input_snapshot、环境/代码信息、时间戳、错误码、幂等信息、执行身份、取消/中断信息|
|Artifact|id、project_id、job_id、kind、format、storage_key、sha256、size_bytes、metadata_schema_version、metadata、validation_state、created_at；只发布完整可读产物|

Session、Job、Artifact 等实际表名由骨架统一，不额外复制“训练任务表/转换任务表/推理任务表”三套状态机。各 Job.kind 的参数使用独立的严格 Schema，不透传任意字典。

Job.kind：dataset_check、train、export_onnx、infer、package。Dataset.state：pending、validating、ready、invalid。Dataset 校验中断时记 invalid 并保存可解释错误，可创建新的校验任务；已 ready 快照不可被失败重试改坏。

Artifact.validation_state：unverified、passed、failed。完成写入但未验证的导出产物不能当作可用 ONNX 模型供后续任务选择。验证失败产生错误报告，可保留受限诊断文件，但不能展示“导出成功”。

历史引用存在时不物理删除 Dataset/Artifact；首版以归档与拒绝不安全删除为主。训练结果必须能定位到确切数据清单、基础权重哈希、参数、随机种子、代码版本和环境。

## 3. 任务状态与唯一终结

合法状态：queued、running、cancelling、succeeded、failed、cancelled、interrupted。终态为后四种，不复活终态。

|当前状态|允许下一状态|条件|
|---|---|---|
|queued|running|Worker 原子领取成功且获得执行槽|
|queued|cancelled|取消请求与领取竞争，取消先成功|
|running|succeeded|进程正常退出、要求的验证通过，原子登记产物并终结成功|
|running|failed|启动/运行/产物验证失败，所属子进程已退出|
|running|cancelling|取消请求原子成功|
|cancelling|cancelled|已确认该任务进程组退出；不得仍占用资源却显示已取消|
|cancelling|failed|取消过程失败，且已确认受管进程组退出；记录失败原因；无法确认退出时保持停领|
|running/cancelling|interrupted|恢复核对确认任务失去执行且没有仍运行的受管子进程|

终态收到取消请求返回当前终态，不改写为 cancelled。成功提交与取消通过状态条件更新竞争：成功先提交则维持 succeeded；取消先写入 cancelling 则不再发布成功产物。正常取消并确认进程退出后进入 cancelled；取消失败且确认受管进程组退出后进入 failed 并记录原因。无法确认退出时继续停领，不用异常绕过进程退出确认。

API 重启不杀独立 Worker。Worker 重启先核对遗留执行再领取新任务；主机重启后未终结任务可在核对后记 interrupted。不得默认自动重训。重试产生新 Job 并记录 source_job_id；实际输入重新校验后冻结。

Worker 单实例保护与领取事务分别存在。记录执行 run_id、Worker 实例、主机启动标识与进程身份；不得仅凭一个过期 PID 杀进程。无法确认遗留进程归属/退出时，停止新领取并报告需要介入，不误杀、不假称已清理。具体 OS 进程管理方案由 T010 记录，T040 以杀进程和重启测试验收。

## 4. 幂等与任务输入

创建任务使用 Idempotency-Key，按用户、操作和键唯一。相同键及规范化参数返回原 Job；相同键不同参数返回 409。记录保留到相关任务按正式保留策略删除，不在未定义情况下随意过期。

任务提交只允许资源 ID 和白名单参数；工作路径由服务端生成。train 首版参数包含预置基础模型 ID、Dataset ID、epochs、batch、imgsz、device、seed，以及经过核验的有限学习率配置。参数上限依据目标机器写入配置，禁止任意 Ultralytics kwargs。训练设备请求与实际设备均记录，失败不能静默降配。

Worker 通过受控参数/配置文件启动固定入口，禁止 shell=True 与把用户输入拼成命令。重任务全部使用同一队列；没有 GPU 时明确能力状态，不把 CPU 或 Fake 伪装成 GPU。

## 5. HTTP 契约

统一前缀 /api/v1。成功响应直接返回 DTO，列表结构固定 items、total、page、page_size。失败结构固定 error.code、error.message、error.request_id，必要时加脱敏 details。请求校验错误和业务错误也使用同一结构。

|接口组|最小接口与语义|
|---|---|
|身份|POST /auth/login，POST /auth/logout，GET /auth/me，POST /auth/change-password|
|项目|GET/POST /projects，GET/PATCH /projects/{id}，POST /projects/{id}/archive|
|数据|GET/POST /projects/{id}/datasets，GET /datasets/{id}，POST /datasets/{id}/check，GET /datasets/{id}/samples|
|任务|POST/GET /projects/{id}/jobs，GET /jobs/{id}，POST /jobs/{id}/cancel|
|日志指标|GET /jobs/{id}/logs?cursor=...，GET /jobs/{id}/metrics?cursor=...|
|产物|GET /projects/{id}/artifacts，GET /artifacts/{id}，GET /artifacts/{id}/download|
|运行|GET /health/live，GET /health/ready，GET /capabilities|
|管理|管理员用户管理、跨项目资源/任务查询；具体 DTO 在 T010 固化|

上传数据集采用 multipart，流式受限落盘；重型解压与校验使用 Job。完整 DTO 在 T010 中明确；未实现接口应返回稳定的 NOT_IMPLEMENTED/501，不能提供虚构成功数据。上传/任务接口返回资源或 Job ID，并明确当前状态，而不是等待训练完成。

日志响应至少包含 items、next_cursor、eof、job_state。游标按任务单调递增，不截断 UTF-8，不无限返回整个日志；失败/取消后也支持最终读取。指标来自结构化真实事件，不靠 UI 正则猜训练进度。

capabilities 按功能返回 available、reason_code、reason、相关已检测版本；训练 CPU/CUDA、ONNX 导出、ONNX 推理、RKNN 分开。探测结果、尚未安装与未验证必须区分。live 不依赖 ML；ready 表示当前 API 基础服务可用，不能等同于所有 ML 功能已验证。

机器可读真相为 Pydantic Schema 生成 OpenAPI，再生成前端类型。T010 冻结生成命令与产物位置；CI/检查入口验证重新生成无漂移，禁止手改生成文件修类型错误。

## 6. 数据集和文件边界

首版 ZIP 内固定 data.yaml、images/train、images/val、labels/train、labels/val，可选 test。允许规范化的单一包裹目录，但不支持任意层级自动猜测。

YAML 只读取允许的类别与受限 split 配置，安全解析；不执行 download 字段、不读服务器绝对路径、不访问外部 URL。明确接受的 names/nc 表达、标签空文件/缺失策略与警告等级，写测试后冻结；不能悄悄丢弃坏样本。

解压前检查路径逃逸、链接、条目数、压缩/解压大小和允许类型。解压到专用 staging，验证成功后再发布；拒绝越界路径、符号链接、设备文件和重复冲突路径。图片解码设置像素/尺寸上限，标注校验类别 ID、行列数、有限数值和归一化坐标范围。上传、解码、训练和任务时间/磁盘均有配置上限。

服务端 storage_key 相对固定存储根；所有资源路径经同一安全解析。下载通过鉴权后的 ID，响应不泄露真实绝对路径。每任务独立 staging；产物先写完再原子发布，随后事务登记；崩溃遗留文件只隔离核对，不自动认成功。

## 7. 模型与推理契约

首版只使用可信预置权重及平台产生的 PT。基础权重与数据集来源、版本、摘要和许可证记录在清单。

ONNX 首版静态输入、batch=1、FP32。opset、导出开关、输入/输出布局在目标工具链烟测后精确锁定，不接受用户任意覆盖。记录 NMS 是否在图内；只能按实际图结构选择后处理，不重复 NMS。

模型元数据包含：类别有序列表、图像输入尺寸、张量布局/类型、RGB/BGR、归一化、letterbox/缩放规则、补边参数、输出含义、置信度与 NMS 规则、坐标还原。将这些元数据随模型与部署包一起保存。

推理响应包含 image_width、image_height、artifact_id、实际 backend/provider、detections。检测框采用原图像素空间的浮点 xyxy，class_id 为从 0 开始的类别序号，score 为 [0,1]；框边界限制到原图，空检测返回空数组。模型间比较前先对齐预处理、阈值、NMS 和坐标。

ONNX 成功验收同时需要结构检查和 ONNX Runtime 执行目标产物；不得回退 PT。加载失败、算子不支持、缺依赖分别报错。性能记录区分预处理/推理/后处理/总耗时及 provider、线程、warm-up 等口径，不比较不同口径的单次时间。

部署包采用固定模板装配，包含模型、manifest/metadata、依赖约束、推理入口、示例输入和 README；禁止运行时调用大模型写脚本。部署包应在不导入平台后端包、不连平台 API 的干净环境中测试。

## 8. 会话与安全

使用服务端会话，密码用成熟密码哈希库；Cookie 配置 HttpOnly、合理 SameSite，HTTPS 交付环境设置 Secure。对改变状态的请求实施明确 CSRF 防护，登录入口也检查来源或等效策略。不同环境的 Cookie 规则要有测试，不在本地开发通过关闭所有安全项解决问题。

管理员初始化不写死密码；令牌/密码/敏感路径不进入日志。对象授权覆盖列表、详情、日志、预览、产物下载、取消与创建任务。只隐藏 UI 按钮不构成权限实现。
