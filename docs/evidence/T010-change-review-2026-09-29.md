# T000/T010 独立 change-review · 2026-09-29

## 范围与基线

审查者以只读方式检查本 Windows 仓库的根提交 `bcf0642`、HEAD `7790b355643faab6a738fdb183232bdef0453d21` 所含 T000/T010 候选，以及 2026-09-29 未提交的状态守卫修复和证据；对照 `AGENTS.md`、`docs/acceptance.md`、T000/T010 任务单和 `.agents/skills/change-review/SKILL.md`。原网页 Work 的 `d5eade0` 历史在本仓库不可得，不在审查范围。审查者没有写文件、提交或推送。

## 发现与修复

**已修复的阻塞级问题：** `docs/architecture.md` 已允许 `cancelling→failed`，但 `backend/app/contracts.py:45` 的集中转换守卫和 `docs/contracts.md` 状态表漏列该边。取消停止失败且已确认受管进程退出时，未来任务无法按架构记录失败。现已在守卫补边，在 `docs/contracts.md` 与 `docs/architecture.md` 明确退出确认条件，并在 `docs/adr/0005-foundation-alignment.md` 记录兼容与回退；`backend/tests/test_contracts_unit.py` 新增未确认退出时拒绝、确认退出时允许、终态不可复活的测试。没有增加状态值或 DB schema，无法确认退出时仍停领。审查者只读复核修复后认为该阻塞已关闭。

其余审查点无新的阻塞级发现：`0001→0002` 隔离副本的关键外键、唯一索引、CHECK 与 `foreign_key_check=[]`；OpenAPI 由真实 `app.openapi()` 生成且 TS 使用生成文件；API/Worker 分进程；业务占位返回 501，异常路径 422/404；Worker 占位子进程只产生失败、排他与遗留停领，不产生训练成功；源码未实现 T020。A01–A04 的 Windows 实测证据与 [补证报告](T010-review-2026-09-29.md) 相符。四个项目 Skill 在当前 Windows 宿主可手动读取，自动触发未验证；Worker 真任务进程方案是后续 T040 的边界。

## 验证与未覆盖

- 审查者独立运行纯契约测试 **6 项**，退出 0；`contract-check` 退出 0。
- 审查者核对修复后的 [完整检查原始日志](T010-review-2026-09-29-bash-check-final.txt)，确认 `bash scripts/dev.sh check` 退出 0：纯契约 6 项、脚本/Worker 9 项、pytest **20 passed**、Vite 构建和契约漂移检查通过；此项是审查原始执行记录，审查者未再完整重跑。
- 审查者以只读 SQLite URI 核对隔离旧库升级副本的外键、唯一索引、CHECK 和 `foreign_key_check=[]`；未迁移真实用户旧库。
- 原 Work Git 历史、真实用户旧库、Windows 真任务进程树取消/重启、ML/ONNX/RKNN、Skill 自动触发均 **NOT_RUN/不可核验**。浏览器实际操作和 HTTP 有文本证据，截图未单独保存为 PNG。

## 结论

**accept（T010/M1）**，当前无剩余阻塞级 finding。A01–A04 的当前 Windows 验收可记 PASS，T010 可标 `accepted`，T020 可标 `ready`；本轮停止在 T010，不自动领取 T020。T000 的 `ML_CHECK_PENDING` 不阻塞轻量 M1：`docs/acceptance.md` 将 ML 依赖与实验留待后续阶段。
