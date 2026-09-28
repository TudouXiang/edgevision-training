# 架构基线

## 组件与边界

| 组件 | 技术 | 边界 |
| --- | --- | --- |
| Web | Vue 3 + TypeScript + Vite + Element Plus（沿用现有 npm/Vite） | 表单、显示真实状态、下载、增量轮询；无训练/转换/推理算法 |
| API | FastAPI + Pydantic | 会话/归属校验、JSON 契约、上传/下载、持久化与排队；不在请求进程跑重任务 |
| 持久化 | SQLite + SQLAlchemy + Alembic | 单库元数据、事务状态；大文件单独落盘 |
| Worker | 独立 Python 进程 | 轮询 SQLite，持有单实例锁，事务领取一个 job，每任务启动新子进程 |
| 算法适配 | Ultralytics，ONNX Runtime（按任务安装） | 受控 YOLO11n 起点、CPU 上验证/推理 ONNX；RKNN adapter 暂不可用 |

浏览器与 API 同源代理；默认仅监听 127.0.0.1。浏览器会话由服务端生成，HttpOnly、SameSite=Lax cookie + 修改请求 CSRF 保护；管理员授权始终在 API 检查。生产启动不自动生成演示用户或样本。初始化管理员使用显式 CLI（T020 实现），不写死密码。PyTorch/Ultralytics/RKNN 不进入轻量 API 的顶层导入。

## 作业状态机

| 原状态 | 事件 | 新状态 | 约束 |
| --- | --- | --- | --- |
| queued | Worker 原子领取 | running | `BEGIN IMMEDIATE`/条件更新；全局仅一个运行中的重任务 |
| queued | 用户取消 | cancelled | 无子进程，直接终态 |
| running | 用户取消 | cancelling | 向子进程组发送中止信号；等待退出/超时强制结束 |
| running | 成功且产物校验 | succeeded | 先落盘、哈希和登记产物，再置成功 |
| running | 执行异常/超时 | failed | 持久化错误码和可脱敏摘要 |
| cancelling | 子进程确认停止 | cancelled | 清理临时产物；保留日志与终态 |
| cancelling | 停止失败/崩溃 | failed | 标记取消失败原因 |
| running/cancelling | 核对确认原受管进程已退出 | interrupted | V1 不自动重放可能非幂等任务；身份/存活无法确认则拒绝领取新任务 |

终态 `succeeded/failed/cancelled/interrupted` 不再改变。job 创建时冻结输入快照与参数；重试是新 job，带 `source_job_id`。只允许 dataset_check/train/export_onnx/infer/package 等白名单 kind。Worker 使用 DB 短事务，无 shell 拼接；进程组终止并等待回收；日志/事件顺序写入。全局文件锁阻止启动第二个 Worker，单任务串行。SQLite WAL、foreign_keys=ON、busy_timeout；数据库与文件共存单机固定 data root，文件落盘和事务之间的异常用临时目录及孤儿清理记录处理。SQLite 的 WAL 仍只有单写者，不能由此推出并行调度能力。[SQLite WAL](https://sqlite.org/wal.html)

## 实时与模型流水线

日志与指标持久化并提供 `GET /jobs/{id}/logs`、`/metrics` 有界游标查询。浏览器约 2 秒轮询，失败时退避；页面重载先 GET 快照，再按游标增量获取，终态最后拉一次。缺乏轮次总量时显示“处理中”，不得合成百分比。高频原始日志保存在文件中，数据库事件只记录状态/结构化指标/有界摘要，避免逐行写放大。

数据集 ZIP 先隔离校验再解压为不可变快照；训练只读取指定快照。PT best/last 文件经哈希登记；ONNX 导出先用 ONNX Runtime CPU 真正载入、核对输入输出与单张样本的检测结果，再把状态置为 validated；真实推理记录输入图片哈希、预处理、阈值、运行时与结果，部署包只包含已验证 ONNX、配置和 Python ONNX Runtime 示例及许可说明。性能记录注明硬件、批量、预热和样本数；绝不推断 RKNN 实机性能。[Ultralytics 导出](https://docs.ultralytics.com/modes/export)，[ONNX Runtime API](https://onnxruntime.ai/docs/api/python/api_summary)。

## 进程与恢复边界

Worker 在 Linux 使用 `flock`，在 Windows 使用本机一字节非阻塞文件锁；`BEGIN IMMEDIATE` 原子领取。启动时如果 DB 记录 running/cancelling 而无法确认对应任务子进程及进程组已退出，拒绝再领任务并报告人工核验；绝不因旧 PID 单独杀进程。记录 `run_id`、`worker_instance`、主机 boot ID 与实际子进程身份；Windows T010 无可信 boot ID 时明确存 `windows-unverified`，绝不将其用于恢复判定。T010 只提供占位进程的受限协议和失败路径；T040 负责 Linux/Windows 真正任务的进程树终止、取消/重启故障注入。见 ADR 0006。

## 不可混用的运行模式

正式 API 与 Worker 不注入测试替身；pytest 使用隔离临时 DB/data root 和替身 runner，并以明确测试配置启动。`reference/` 中 Next.js 演示源保持只读：假概览、计时训练、转换和管理员监控不能作为运行状态。逐页复用设计时须替换为真实 API，未完成入口禁用并标记。
