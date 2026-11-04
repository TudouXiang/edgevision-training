# 本地文件存储规则

根目录由 `PLATFORM_DATA_ROOT` 设置（默认仅用于本地开发的 `./data`），正式运行使用独立目录且仅当前操作系统用户可写；相对根目录 `storage_key` 由服务端生成 UUID/哈希分层键，拒绝用户指定的路径、`..`、绝对路径和软链接穿越。

T030 已在 staging/纯校验核心实施：单 ZIP 512 MiB、multipart 额外 128 KiB、中央目录 32 MiB、最多 20000 条目、解压总量 2 GiB、单成员 512 MiB、大成员及聚合压缩比 200:1、图片文件 50 MiB/3000 万像素；YAML/label 的更细限制见 ADR 0008。T040 候选已接入真实 Worker 与 Linux 故障测试，Windows 和最终 CI 验收范围见 T040 报告。

```
data/
  platform.db
  worker.lock
  uploads/<uuid>.part
  datasets/<dataset-id>/source.zip
  datasets/<dataset-id>/validations/<run-id>/snapshot/...
  datasets/<dataset-id>/validations/<run-id>/report.json
  datasets/<dataset-id>/validations/<run-id>/manifest.json
  jobs/<job-id>/runs/<run-id>/input.json
  jobs/<job-id>/runs/<run-id>/identity.json
  jobs/<job-id>/runs/<run-id>/drained.json
  jobs/<job-id>/runs/<run-id>/logs.jsonl
  jobs/<job-id>/runs/<run-id>/evidence.json
  jobs/<job-id>/runs/<run-id>/bundle/... (未发布/取消/崩溃隔离目录)
  artifacts/<artifact-id>/<safe-filename>
```

上传流式写入隔离 `.part`，按真实字节限流并计算 SHA-256；flush/fsync 后做轻量 ZIP 预检，再在最终短事务重新鉴权并原子移动为新 Dataset 的 source.zip。HTTP 不做重型解压/图片解码。纯校验服务安全逐成员解压到一个不存在的目录，核对实际发出字节、图片和 YOLO 标签；成功结果仍须由 T040 Worker 持久化 report 并发布 ready，不能由调用者直接当作训练输入。

产物只在完成真实文件存在、非零长度、哈希计算及格式/推理验证后登记；`.part` 与孤儿文件清理时不触碰被引用且已验证的产物。下载只根据数据库 artifact ID 查找服务端生成的 storage_key，再做 root containment、regular file 和 SHA-256 检查，返回下载审计信息。不要公开 data 目录或直接映射 URL；文件名仅用于 Content-Disposition 显示并转义。

禁止把上传内容中的脚本当命令执行。ZIP/模型不可信，模型反序列化风险需限制可用权重来源；V1 用户上传 PT 的执行安全隔离与是否开放必须先由 T6 给出方案，本基线默认**不开启任意用户上传权重**。


T040 单个协议文档/报告上限 16 MiB，可能先于 20000 个条目触发（例如大量长路径/warnings），此时 Job OUTPUT_CAPACITY_LIMIT/failed、Dataset pending，不伪造 ready 或 invalid。每 run bundle 含 snapshot/report/manifest，树退出后重验输入及全部输出 SHA，先提交 publication intent，再同卷 rename，最后一个短条件事务发布。取消赢事务时不登记产物，可能留下未引用目录；这些目录隔离保留，不自动删除用户文件或重建成功。正式物理清理仍须后续明确保留策略。进程崩溃边界已测试，不声称硬件掉电保证。

## T050 增量

`models/base/{yolo11n.pt,manifest.json}` 仅操作员供给固定资产；`training-capability.json` 是受管实际探针产生的
版本化能力记录，`training-probe-active.json` 保留探针执行身份/恢复入口。训练 run 内有独立 dataset、私有环境配置、
框架运行目录和单独有界 `metrics.jsonl`。仅 `best.pt`、`last.pt`、`metadata.json` 组成可发布 bundle，
同卷 rename 到 `trained/{job_id}/{run_id}` 后短事务同时登记两条 PT Artifact 与成功终态。
物理孤儿清理没有自动实现；不会用孤儿文件重建成功。新增记录复用现有 JSON 列与 metrics 表，无迁移。
