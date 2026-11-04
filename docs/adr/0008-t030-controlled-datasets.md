# ADR 0008：T030 受控数据集接收与校验边界

状态：accepted（2026-11-04；Linux 核心范围，独立审查及真实 CI 见 T030-browser-acceptance-2026-11-04.md）

## 问题与既有约束

`0002_foundation` 已有不可变 Dataset 的版本、父快照、源 ZIP、snapshot、report、类别、计数和 manifest 字段，状态固定为 pending/validating/ready/invalid。T030 需要安全接收 ZIP、冻结 YOLO 数据规则并提供可由后续 Worker 调用的校验核心；T040 才负责异步 Job、状态转换与 ready 发布。若在 HTTP 请求中完成解压/图片解码，或在没有 Worker 时返回假 Job/ready，会破坏既有进程边界。

## 决定

### 上传、存储与状态

- `POST /projects/{id}/datasets` 只接受一个名为 `file` 的 multipart ZIP。API 在读取 body 前校验会话、Origin、CSRF、owner 与项目未归档；流式消费原始 ASGI body 时同时限制整个 multipart 和真实文件字节，不依赖 `UploadFile` 的临时文件上限。
- ZIP 流入服务端生成的 `uploads/<uuid>.part`，边写边算 SHA-256，完成后 flush/fsync。只做中央目录预检，不在 HTTP 请求内解压、解析 YAML 或解码图片。
- 注册前用短 `BEGIN IMMEDIATE` 再次鉴权并检查归档状态；同名导入在事务中分配递增 version 和 parent_id。源文件原子移动到新建且独占的 `datasets/<dataset-id>/source.zip`，记录真实哈希和字节数，状态为 pending。失败只清理本次新建路径。
- 每次重新上传都产生新 Dataset ID/版本；没有修改、覆盖 ready snapshot 的接口。`/datasets/{id}/check` 在 T040 前继续返回 501，pending 数据集不能预览或训练。

### ZIP 与资源上限

- 单 ZIP 512 MiB，multipart 额外开销 128 KiB，最多 20,000 条目，声明解压总量 2 GiB，单条目 512 MiB；大于 1 MiB 的成员压缩比不超过 200:1。
- 只接受 stored/deflate、受支持的常规标志；拒绝加密、patched/strong-encryption、符号链接和其它特殊文件。
- 路径必须是 UTF-8 可表达的 NFC、正斜杠相对路径；拒绝绝对路径、`.`/`..`、反斜杠、控制字符、Windows 保留名/字符/ADS、尾随点或空格、过长组件、重复/大小写碰撞和文件/目录碰撞。
- 根必须直接包含 `data.yaml`，或所有条目位于唯一的一层 wrapper 且其中包含 `data.yaml`。不猜测多层根。文件只允许 `data.yaml`、小写 `.jpg/.jpeg/.png` 的 `images/{train,val,test}/...` 与小写 `.txt` 的镜像 `labels/...`。

### YAML、图片与标签

- `data.yaml` 最大 64 KiB，UTF-8，安全解析且限制 32 层/10,000 节点；拒绝 alias、anchor、显式 tag、重复键和未知字段。`path` 只能省略或为 `.`；train/val 必须是对应 `images/...` 字符串；test 配置与文件必须同时存在或同时不存在；不执行 download、不接受 URL 或服务器路径。
- `names` 接受非空字符串列表，或从 0 开始连续的整数键 mapping；最多 1,000 类，类别名去除大小写后仍须唯一。`nc` 可省略；存在时必须是整数并等于 names 长度。
- 图片文件最大 50 MiB、最多 3,000 万像素，只允许实际内容与扩展名一致的单帧 JPEG/PNG；既执行 Pillow verify，也实际 decode。损坏、元数据解压异常或超像素均失败。
- 每张图片必须有镜像 label。缺 label 是错误，避免把漏标静默当背景；孤立 label 和同 stem 多图片是错误。空或仅空白 label 是显式背景样本，允许但写 `LABEL_EMPTY` warning。
- 每个非空标签行必须正好是 `class_id x_center y_center width height`。class_id 是范围内的十进制非负整数；坐标必须有限，中心在 `[0,1]`，宽高在 `(0,1]`，整个框也必须落在归一化图像内。每 label 4 MiB、单行 4096 bytes、最多 100,000 个框。

### 校验结果与预览

- 纯服务输入源 ZIP 与一个不存在的输出目录；不访问网络/数据库，不发布状态。它逐成员安全写出、核对实际发出字节/CRC，失败删除本次目录并返回稳定 code、相对 path 和可选 line。
- 成功结果包含固定类别顺序、split/图片/框/背景计数、逐文件 SHA-256、确定性 snapshot digest、warnings，以及至多 100 个 sample/每 sample 200 个框的预览摘要。完整验证成功不等于数据库 ready；T040 还须持久化报告并原子发布 snapshot/状态。
- `GET /datasets/{id}/samples` 改用专用 `DatasetSamplePublic`，不再错误复用 Artifact DTO。只有已有 ready 且 manifest schema 可验证的数据集可读；图片通过 owner-aware opaque sample ID 路由提供，不公开 data root 或接受客户端文件路径。

## 兼容性、依赖与迁移

不新增迁移、不修改 0001/0002；旧 pending 数据仍可读，旧 ready 若没有合法 preview manifest 会明确返回 `DATASET_PREVIEW_UNAVAILABLE`，不合成样本。OpenAPI 为加法式 DTO/图片路由变更，前端类型重新生成。轻量依赖增加 Pillow、PyYAML、python-multipart；不增加 Torch/Ultralytics/Worker 运行时。

## 未选方案

- `UploadFile`/`request.form()`：Starlette 的字段上限不限制 file part 在进入路由前的完整 spooling，不能作为安全边界。
- HTTP 同步完整校验：会把不可信解压和图片解码放入长请求，并绕过 T040 Worker 的取消/恢复语义。
- 缺 label 自动当背景、自动修复框或猜测目录：会掩盖数据错误并改变训练输入。
- 覆盖同名 ready 数据集：破坏训练/论文实验的输入可追溯性。

## 回退与验证

代码回退不需数据库降级；回退前保留已登记源 ZIP 和 Dataset 行，不能直接删用户数据。验证覆盖正常 root/wrapper、names 两种表达、显式空 label、所有上述 ZIP/YAML/图片/标签失败、实际发出超限、staging 中断清理、同名新版本、归档竞态、owner/admin 读取、pending 禁预览和 ready 有界预览。T040 Worker 接线、真实 upload→ready 浏览器流程、训练输入绑定保持未执行。
