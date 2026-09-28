# 本地文件存储规则

根目录由 `PLATFORM_DATA_ROOT` 设置（默认仅用于本地开发的 `./data`），正式运行使用独立目录且仅当前操作系统用户可写；相对根目录 `storage_key` 由服务端生成 UUID/哈希分层键，拒绝用户指定的路径、`..`、绝对路径和软链接穿越。

T010 候选资源上限：单 ZIP 上传最大 512 MiB、解压总大小 2 GiB、ZIP 条目最多 20000、图片单张最多 3000 万像素。这些约束尚未由上传处理器实现，T030/T040 须在目标机器核验并配置收紧，不得将文档数字误报为已执行安全检查。

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

上传流式写入隔离 `.part`，校验大小、ZIP 条目数/解压总量/压缩比、重复路径、绝对路径、`../`、符号链接、危险文件类型和 YOLO 标签；先写、`fsync`、SHA-256，再在同卷原子重命名。训练读取完成验证的不可变 snapshot，绝不在解压源目录直接写训练输出。标注 `class_id` 范围、归一化 x/y/w/h、train/val 分割及图片标签对应关系逐项出可下载报告；不能修补数据后将原快照标为有效。

产物只在完成真实文件存在、非零长度、哈希计算及格式/推理验证后登记；`.part` 与孤儿文件清理时不触碰被引用且已验证的产物。下载只根据数据库 artifact ID 查找服务端生成的 storage_key，再做 root containment、regular file 和 SHA-256 检查，返回下载审计信息。不要公开 data 目录或直接映射 URL；文件名仅用于 Content-Disposition 显示并转义。

禁止把上传内容中的脚本当命令执行。ZIP/模型不可信，模型反序列化风险需限制可用权重来源；V1 用户上传 PT 的执行安全隔离与是否开放必须先由 T6 给出方案，本基线默认**不开启任意用户上传权重**。
