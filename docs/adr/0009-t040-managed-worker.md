# ADR 0009：T040 受管任务进程与校验发布

日期：2026-11-04。状态：待架构审查，审查前不开始大规模实现。范围仅 T040；T050 仍阻塞。

## 现实、风险与决定

T030 已通过 Linux 核心验收；当前 Worker 是占位实现。`Popen` 后才登记 PID 存在启动窗口；只观察根进程退出不能证明孙进程退出。T040 保留单机 SQLite、独立单实例 Worker、FIFO 全局单重任务槽和既有状态枚举，不引入调度服务或训练算法。

每个 run 使用短命 guardian，固定任务入口只接受服务端生成的输入文件。guardian 先建立 OS 容器及任务启动门，写入绑定 job/run 的身份记录；Worker 用条件事务持久化身份后才发送 GO。Worker 到 guardian 的独占控制管道 EOF 表示中止；runner 不继承 Worker 锁、控制写端或 Windows Job handle。guardian 不执行用户脚本，不是恶意代码沙箱。

Linux guardian 是独立 session 的 child subreaper，记录 boot ID、PID、`/proc` start ticks/session；对真实后代使用保留的身份或 pidfd 发信号，重复收养/回收至 `ECHILD`。根进程退出不释放槽；残留后代先终止再回收。Windows guardian 持有唯一命名的 Job Object，`KILL_ON_JOB_CLOSE`、不允许 breakaway、句柄不继承；以 `STARTUPINFOEX` 的 `PROC_THREAD_ATTRIBUTE_JOB_LIST` 原子加入 Job 并 `CREATE_SUSPENDED`，保留 process/primary-thread handle，GO 后才 `ResumeThread`。取消用 `TerminateJobObject` 并查询 active process 数为零。失败不回退到裸 Popen/taskkill。

仅在整个受管树确认退出后写入版本化、run 绑定的 drain receipt；Worker 还须等待 guardian 退出才允许终态及发布。guardian 被强杀而缺 receipt 时，即使根 PID 已消失也拒绝释放槽。Linux 主机 boot ID 变化证明旧主机任务消失；Windows 无经验证的 boot identity 时保持安全阻塞，不使用 `windows-unverified` 作恢复证据。新 Worker 只将已证明结束的遗留执行记 interrupted，不自动重跑。API 重启不触碰 Worker。

领取后、启动之前使用持久化 launch phase。`claimed` 且从未写入 spawning 的任务可证明未启动；`spawning` 后没有身份或 receipt 的窗口一律歧义阻塞。guardian 即使在 Worker 消失后启动，也必须先检查控制 EOF，并只做清理。每 run 使用独占目录，不能复用旧 receipt。

## 最小迁移及 HTTP 兼容性

新增迁移 `0003_worker`，不改 0001/0002：jobs 增加 `process_identity_json`、`launch_phase`、`publication_json`；datasets 增加可空 FK `validation_job_id`。旧 running/cancelling 记录无可信身份时保留并阻塞。迁移在隔离空库和 0002 样本验证；回退前必须停 API/Worker 并核实无活动任务，新字段只在此条件下可移除，已发表数据不得由回退删除。

复用唯一状态守卫，新增统一 CAS + 同事务 status event 写入入口。Dataset 检查输入冻结 archive key/size/SHA。规范化请求 hash、Job、幂等键在一个 BEGIN IMMEDIATE 事务写入；同键同参数返回原 Job 的真实当前状态，同键不同参数 409。因此 `JobAccepted.state` 从 queued literal 扩为 JobState。`jobs.owner_id` 记录实际提交 actor，对外对应 created_by；资源所有权/可见性/取消权始终由所属 Project.owner_id 加管理员权限决定，不伪造管理员代发起时的创建者，也不新增冗余字段。另一个键指向仍在校验的同一 Dataset 返回同一活动 Job 并建立该键关联；ready 新检查返回 409，失败/取消后的重试创建新 Job。owner/admin、CSRF、项目归档检查仍在最终写事务。未实现 kind 501。

提供 owner-aware Job list/detail/cancel/logs/metrics 及报告 Artifact list/detail/download。Dataset DTO 增加 validation_job_id/report_artifact_id 便于刷新恢复；新增字段可空。游标版本化且绑定 job 和流，错误/跨任务游标 422；日志总量、单行和分页字节均有硬上限，达到捕获上限后仍持续 drain，不生成虚构指标。

## 真实校验与不可变发布

固定 adapter 仅在任务子进程调用 T030 `validate_dataset_archive`。输出严格版本化 evidence，包含 job/run、输入 archive SHA、report/manifest 和每个 snapshot 文件的相对路径、角色、大小、SHA。Worker 在树退出后重新核对冻结输入和全部输出，退出码 0 但缺失/损坏文件必失败。

报告和 snapshot 放入同一 run bundle，Worker 先提交 publication intent，再在同卷独占目标执行原子 rename，最后一个条件事务登记报告 Artifact、更新匹配 validation_job_id 的 Dataset，以及 Job 唯一终态。有效数据 ready/succeeded；有真实校验错误的报告 invalid/failed。取消先进入 cancelling 时不得发布成功；成功先提交后取消返回终态。发布目录不能覆盖现有快照。rename 后 DB 提交前崩溃的目录保留为未引用隔离证据，恢复记 interrupted，不从目录存在重建成功。保证进程崩溃一致性；不声称验证了任意硬件断电/文件系统掉电持久性。

## 不采用的更小方案

仅 process group / `taskkill /T` 无法覆盖 root 先退出、setsid、PID 复用以及初始进程在加入 Job 前逃逸。单独记 PID + child.poll 不能证明资源已释放。仅将文件写入后更新 DB 不能把取消、重复完成和 stale run 竞争统一。上述 guardian/receipt 和加性迁移是支持既有真实恢复契约的最小调整。

## 实施检查点与证据门槛

1. 架构放行后实现迁移、状态/幂等/API 与针对性隔离测试。
2. Linux/Windows guardian、真实固定 adapter、日志和 immutable publication；测试只能在隔离 helper 显式注入故障，不增加生产可选 Fake。
3. 真实进程覆盖竞领、取消/完成、孙进程/根先退/TERM 抵抗、Worker kill 前后门、guardian kill、身份不符、缺失/损坏输出、输出洪泛、API 重启、rename-before-DB 及 commit-before-response。
4. 前端真实上传→检查→排队/日志→ready 或 invalid/报告；刷新、切换、重复点击、会话失效与最终日志轮询。Linux Chromium 在现有托管 CI 运行，不重试本地禁止的 socket 启动。
5. Windows 标准托管 runner 执行真实进程测试（不得 skipped green）；完整主机重启无法在托管 job 实测，明列 NOT_RUN 与安全阻塞限制供闸门审查。
6. 生成 OpenAPI/TS、全量 check、独立只读审查、精确提交 CI；T040 标 review_required，不自行接受或开启 T050。

官方资料：
- https://man7.org/linux/man-pages/man2/PR_SET_CHILD_SUBREAPER.2const.html
- https://man7.org/linux/man-pages/man2/pidfd_send_signal.2.html
- https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute
- https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes
- https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
- https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-terminatejobobject

## 启动/恢复决策表及诊断

| 持久化阶段/证据 | 新 Worker 决策 | 对运维的诊断 |
| --- | --- | --- |
| claimed，尚未进入 spawning | 自动 interrupted；确定未尝试创建 guardian/runner | WORKER_INTERRUPTED_BEFORE_LAUNCH |
| spawning，尚无可信身份/receipt | 停领；不推测没启动，不发信号 | RECOVERY_BLOCKED_DRAIN_UNCONFIRMED |
| prepared，身份已提交但 GO 尚未持久化记录；执行可能已开始 | 等 guardian 因 EOF 回收后，凭 receipt + guardian 退出自动 interrupted；证据不齐停领 | RECOVERY_BLOCKED_DRAIN_UNCONFIRMED |
| go_authorized / draining，有匹配 receipt 且 guardian 已退出 | 自动 interrupted；不重新执行/不重建成功 | WORKER_INTERRUPTED |
| guardian 活着或 receipt 未出现 | 本次恢复有界等待控制 EOF 的清理，超时退出码 4；Job 留在活动态/槽仍占用，不无限假装恢复中 | RECOVERY_BLOCKED_DRAIN_UNCONFIRMED |
| guardian 已死但无 receipt，包括强杀 guardian | 停领；不存在的根 PID 不足以证明后代退出 | RECOVERY_BLOCKED_DRAIN_UNCONFIRMED |
| Linux 可信 boot ID 与记录不同 | 自动 interrupted；旧 host 的进程不可能仍存活 | HOST_RESTARTED |
| legacy 无身份或 Windows 无 receipt 的重启 | 停领，报告需人工核验；禁止直接更改数据库状态以绕过 | RECOVERY_BLOCKED_IDENTITY_UNVERIFIED |

诊断仅给 job ID、稳定错误码及“无法确认旧任务进程已退出，已停止领取新任务，请核验受管进程及恢复记录”；不泄露绝对路径或用户内容。恢复未通过时不会返回成功退出码，不会领取排队任务。硬件/主机重启证据缺口明确列入验收报告。

项目归档只禁止创建新 Job；既有排队/执行中的 Job 按冻结输入继续，仍允许 owner/admin 读取、取消和下载历史报告，不因归档隐式杀进程。已存在的同键幂等重放属于读取既有提交而非新任务，可返回原 Job；归档期间全新键提交一律 409。

架构方向于 2026-11-04 放行实施，最终验收仍待实际证据。取消/中断/基础设施失败统一将匹配 validation_job_id 且仍 validating 的 Dataset 恢复 pending；只有真实数据校验错误才置 invalid。此处最小调整旧 contracts.md 的“校验中断→invalid”语义，区分未验证和数据错误。提交新 Job 时清空当前 report_key；历史报告 Artifact 与原 Job/文件保留，绝不把旧报告冒充此次结果。重试新建 Job，ready 不能重试。environment_json 仅白名单 Python 版本、平台、协议版本，不读取/保存整份环境变量；公共日志为固定脱敏消息，不输出服务器绝对路径或内部 traceback。

GO 发送与 cancelling 的条件检查在同一短写事务内串行；身份在前一事务已提交。GO 后事务提交前崩溃可能保留 prepared，所以 prepared 绝不被解释成“未执行”，仍须完整 drain receipt。


## Windows 虚拟环境解释器兼容性修正

真实 Windows CI 暴露 CPython venv redirector：Popen 创建的 python.exe 可能只负责创建并等待实际解释器，因此不能把 redirector PID 当成 guardian 自身 PID。采用 [CPython 3.12.10 multiprocessing 官方同款启动协议](https://github.com/python/cpython/blob/v3.12.10/Lib/multiprocessing/popen_spawn_win32.py#L55-L62)：仅对当前 Windows 虚拟环境，使用 `sys._base_executable` 并在复制的子进程环境中设置 `__PYVENV_LAUNCHER__=sys.executable`，保留隔离依赖；不修改全局环境。Worker→guardian 以及测试/浏览器编排中用于身份或终止的 Worker/API Popen 句柄均指向实际解释器。原有出生身份、严格匹配与 receipt 退出证明完全保留；历史不匹配记录仍阻塞，不采信另一份自报身份修复旧记录。

Windows runner 的原子 Job Object 启动 ABI 不变：记录的 root 是 CreateProcessW 初始创建的进程，可能为 redirector，不宣称等于 adapter 自身 PID。它在 GO 前 suspended，实际 adapter 与后代仍继承外层 Job；根句柄退出与外层 ActiveProcesses=0 同时成立才视为整树清空。原有 nested Job、强杀 guardian 的 KILL_ON_JOB_CLOSE 与孙进程用例继续执行，不绕开 venv、不削弱测试。新增原生探针比较活着的子解释器 PID/出生身份、venv prefix/可执行身份以及项目依赖可导入性；CI 只输出布尔诊断，先于完整矩阵失败即停止。
