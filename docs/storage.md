# 本地文件存储规则

根目录由 `PLATFORM_DATA_ROOT` 设置（默认仅用于本地开发的 `./data`），正式运行使用独立目录且仅当前操作系统用户可写；相对根目录 `storage_key` 由服务端生成 UUID/哈希分层键，拒绝用户指定的路径、`..`、绝对路径和软链接穿越。

T030 候选已在 staging/纯校验核心实施：单 ZIP 512 MiB、multipart 额外 128 KiB、中央目录 32 MiB、最多 20000 条目、解压总量 2 GiB、单成员 512 MiB、大成员及聚合压缩比 200:1、图片文件 50 MiB/3000 万像素；YAML/label 的更细限制见 ADR 0008。T040 仍须在 Worker 接线和目标机器故障注入中复核，不能把纯服务测试说成异步链路完成。

```
data/
  platform.db
  worker.lock
  uploads/<uuid>.part
  datasets/<dataset-id>/source.zip
  datasets/<dataset-id>/snapshot/...
  datasets/<dataset-id>/report.json
  jobs/<job-id>/work/...        (临时，失败后清理)
  jobs/<job-id>/events.jsonl
  artifacts/<artifact-id>/<safe-filename>
```

上传流式写入隔离 `.part`，按真实字节限流并计算 SHA-256；flush/fsync 后做轻量 ZIP 预检，再在最终短事务重新鉴权并原子移动为新 Dataset 的 source.zip。HTTP 不做重型解压/图片解码。纯校验服务安全逐成员解压到一个不存在的目录，核对实际发出字节、图片和 YOLO 标签；成功结果仍须由 T040 Worker 持久化 report 并发布 ready，不能由调用者直接当作训练输入。

产物只在完成真实文件存在、非零长度、哈希计算及格式/推理验证后登记；`.part` 与孤儿文件清理时不触碰被引用且已验证的产物。下载只根据数据库 artifact ID 查找服务端生成的 storage_key，再做 root containment、regular file 和 SHA-256 检查，返回下载审计信息。不要公开 data 目录或直接映射 URL；文件名仅用于 Content-Disposition 显示并转义。

禁止把上传内容中的脚本当命令执行。ZIP/模型不可信，模型反序列化风险需限制可用权重来源；V1 用户上传 PT 的执行安全隔离与是否开放必须先由 T6 给出方案，本基线默认**不开启任意用户上传权重**。
