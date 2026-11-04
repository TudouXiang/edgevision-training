# 合成 SQLite + 文件备份恢复练习（2026-11-04 UTC）

状态：**限定合成练习已通过独立复核；仅所列合成样本 PASS，不是全平台恢复验收。**

基线 `b9cbc568774d8ddfdfb4a312009ebf39bebe4437`，独立分支
`test/synthetic-backup-recovery`。手动读取 AGENTS、feature-delivery、experiment-evidence、
存储/Schema/ADR 0009 恢复协议后执行。没有修改生产代码、迁移、API 或 E/I/P/T070 闸门。

## 预先限定范围与判断标准

- 入口只有 pytest 测试，无 source/destination 命令行参数。每个用例自行创建 TemporaryDirectory，
  覆盖本测试进程的 PLATFORM_DATA_ROOT，使用真实 Alembic 迁移到 `0003_worker`。
  不读取已有用户数据库，也不连接服务；仅复用已安装的轻量 Python 环境。
- 合成行覆盖 users、sessions、projects、datasets、jobs、job_events、metrics、artifacts、
  idempotency_keys 和 alembic_version。直接填入的是**存储保真样本**，不是 API/Worker 产生的业务成功。
  Job 为 failed、Dataset 为 pending、Artifact 为 unverified；无可用模型、训练或推理产物。
  source.zip 是明确标记的普通合成字节，不能作为真实 ZIP/校验成功证据。
- 文件白名单仅六个：source.zip、snapshot 中的一份标签、manifest.json、report.json、run input.json
  和 logs.jsonl。样本内容及完整相对路径在测试 FILES 常量中。按不可变快照的字节保真要求核对，
  不声称验证了文件系统只读权限。未覆盖图片、PT/ONNX、完整发布束、所有平台目录或真实资产。
- **复制期间所有写者停止**是由测试构造保证的前提，不是这个工具能够替操作员证明的事实。
  保留一个不再写入、无未提交事务的 SQLite 连接，只为让已提交 WAL 帧仍存在。
  不启动 API、Worker、guardian 或任务。测试也拒绝 queued/running/cancelling 样本，
  但“没有活动 Job”不能证明外部写者已停止。
- 通过标准预先确定：恢复全部表的值逐列相同；SQLite integrity_check 为 ok、foreign_key_check 为空；
  六个文件和数据库备份的 SHA-256/清单一致；Artifact 与 Dataset 的数据库摘要/大小匹配恢复字节。
  原始 DB、WAL、应用文件字节保持不变。SQLite 读连接可能更新 SHM 协调信息，因此不比较 SHM；
  测试结束关闭连接时正常 checkpoint/临时目录清理也不属于“复制期间不改源”的断言。

## 已执行与结果

23 项新增用例通过：

1. 对照组只复制 platform.db，读取 users 数量为 0，明确证明遗漏 WAL 会丢失此样本已提交行。
2. SQLite backup API 读取包含 WAL 的数据库快照，再复制固定六文件，恢复到全新目录；
   表数据、外键、完整性、字节/摘要均通过，恢复不依赖源 WAL 文件。
3. 数据库、六个文件、清单分别缺失或损坏：16 个分支均拒绝，尚未创建恢复目录；源文件及行不变。
4. 多余未登记文件拒绝；已有恢复目标拒绝且原 marker 文件不变。
5. queued/running/cancelling：3 个分支在创建备份目录前拒绝。
6. 故意构造数据库外键破坏并刷新快照摘要，仍由 SQLite 外键检查拒绝。

附带既有 `0001` 合成副本迁移测试及纯契约回归通过。总计 **30 passed、8 subtests passed**，
27 条已有依赖弃用警告；退出码 **0**。此次首次运行未执行全量后端、前端或远端 CI；后续复核另记如下。

执行时间：2026-11-04 17:00 UTC，Linux，Python 3.12.14、SQLite 3.53.1、pytest 9.1.1、Alembic 1.20.0。
工作目录为独立 worktree 的 backend；使用既有轻量隔离 Python 环境执行下列命令（路径已匿名化）：

```sh
python -m pytest tests/test_synthetic_backup_recovery.py tests/test_bootstrap.py::test_legacy_0001_copy_upgrade_preserves_rows tests/test_contracts_unit.py -q
```

[测试源码](../../backend/tests/test_synthetic_backup_recovery.py)保留全部合成构造与断言。
原始输出仅保留在本地检查档案；公开材料仅保留上述匿名汇总。首次命令因工作目录前缀重复而未运行，
修正后扩充样本并得到上述最终结果。不要将测试内部的复制辅助函数用作真实用户数据备份程序。

## 独立复核（2026-11-04 17:09 UTC）

复核候选 `8bb2c7184f065d03cccabee106b1ee3a06b16511` 的测试及 README/验收文档，
以公开 `b9cbc568774d8ddfdfb4a312009ebf39bebe4437` 到候选工作树的八文件端点差异为范围，
不把重建分支的提交集合等同于本轮新增范围。结论 **accept（仅此限定范围）**，未发现阻塞。
独立重跑以下命令，退出 **0**：**27 passed**，23 条已有 Alembic 弃用警告。

```sh
python -m pytest tests/test_synthetic_backup_recovery.py tests/test_docs_scope.py -q -p no:cacheprovider
```

其中 23 项为合成恢复、4 项为文档链接/范围回归。复核确认 WAL 对照、固定文件保真、
源 DB/WAL/应用字节不变及全部已列负向分支；未连接服务或真实用户库，未执行模型。
README/验收文档清楚区分当前阶段与历史骨架，普通 CI 不解除真实 E/I/P 闸门。
后续远端普通 CI 的历史计数由交付者另行直接读取精确 run/job 日志核验，不从静态文档推断。

额外覆盖缺口：未以“刷新清单后的物理 SQLite 页损坏”单独触发 integrity_check 失败；
Dataset size 由固定 fixture 构造、全表相同和文件字节相同间接验证，未另设单独查询断言。
这不扩大本练习的生产适用范围。

## 轻量整合复跑（2026-11-04 17:08–17:13 UTC）

在交付 worktree 的同一候选源码上执行下列聚合命令，显式清空原生策略测试的 opt-in 目录，
保持真实 ML 执行关闭。后端 **398 passed、9 skipped**，前端 **47 passed**，
Vue/TypeScript/Vite 构建及 OpenAPI/TS 契约漂移检查通过，聚合退出码 **0**。
新增 27 项正是上述 23 项合成恢复与 4 项文档回归；178 条警告为已有依赖弃用及负向 ZIP 样本警告。

```sh
EDGEVISION_ML_POLICY_ROOT='' EDGEVISION_ONNX_POLICY_ROOT='' EDGEVISION_RUN_ISOLATED_ML=false python3 scripts/dev.py check
```

另外在 backend 执行 `python tests/http_restart_probe.py`，退出 **0**，
`http_api_restart`、`independent_worker`、`tree_exit` 三项 passed。
该探针使用自己的临时夹具，不是对本恢复副本启动服务的测试，不补齐下方未执行项。
原始本地日志未公开。远端 CI 必须核对后续发布的精确 SHA，不能沿用基线 run 的结果。

## 运维含义与未执行项

现有文档“停止 API/Worker、做一致性备份、在副本迁移”不能简化为只复制 platform.db。
真实整个平台的备份至少需协调所有写者（含受管后代/探针），保留数据库与全部需要的受控数据文件、
记录版本/清单并在独立目标验证引用关系。活动执行的身份/receipt 不能因恢复而伪造，
不得修改 Job 状态绕过 ADR 0009 的安全停领，也不能从孤儿目录重建成功。

本测试没有实现这种生产流程：不接受任意目录、不发现实际文件全集、不验证符号链接/恶意备份、
不提供加密/签名或会话处置策略，不保证复制失败中途的原子回退。清单仅检测意外缺失/损坏，
不是抵御同时篡改数据和清单的认证机制。不能据此恢复任何真实用户库。

以下均**未执行/未验收**：实时写入备份、实际服务重启后的恢复可用性、完整平台运行目录恢复、
主机重启/物理掉电/磁盘耗尽、Windows 本轮恢复、跨版本恢复/升级兼容全集、真实用户数据、
ML/ONNX/ORT/浏览器/硬件。没有网络、下载、Docker、训练、原生模型导入或资产处理。
E 未 accepted，I/P/T070 的既有闸门保持不变。
