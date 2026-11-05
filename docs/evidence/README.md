# 证据目录

本目录保存分阶段实现报告、独立审查、CI 验收和脱敏原始记录。先读[项目状态](../status.md)与[验收矩阵](../acceptance.md)，再核对报告绑定的精确提交、日期、环境、命令及限制。目录或报告存在本身不代表测试通过。

## 阶段入口

| 阶段 | 结论与范围 | 过程、审查或补充 |
| --- | --- | --- |
| T000 盘点 | [盘点报告](T000-report.md) | [早期 Linux 启动记录](bootstrap-2026-09-23.md) |
| T010 骨架 | [Windows 复核](T010-review-2026-09-29.md)、[独立审查](T010-change-review-2026-09-29.md) | [地基报告](foundation-report.md)、[跨平台入口](portable-bootstrap-2026-09-28.md) |
| T020 身份与项目 | [真实浏览器验收](T020-browser-acceptance-2026-11-04.md) | [实现报告](T020-report.md)、[独立审查](T020-change-review-2026-11-04.md) |
| T030 数据集核心 | [Linux 核心浏览器验收](T030-browser-acceptance-2026-11-04.md) | [实现报告](T030-report.md)、[独立审查](T030-change-review-2026-11-04.md) |
| T040 受管 Worker | [跨平台验收及未实测限制](T040-cross-platform-acceptance-2026-11-04.md) | [实现与失败历史](T040-report.md)、[独立审查](T040-change-review-2026-11-04.md) |
| T050 训练 | [固定 Linux CPU 验收](T050-ci-acceptance-2026-11-04.md) | [实现报告](T050-report.md)、[环境与资产前检](T050-preflight-2026-11-04.md) |
| T060 导出重建 | [源码检查点及未验收边界](T060-rebuild-checkpoints.md)、[普通 CI 范围](T060-source-ci-2026-11-04.md) | [后端范围](T060-export-rebuild-core.md)、[重建记录](T060-rebuild-recovery-2026-11-04.md) |

T060 的计划、源码检查和普通 CI 不能代替真实模型验收；E / I / P 的最新结论以项目状态及对应实际执行报告为准。T070 尚无完整平台验收报告，不从前置阶段拼接推断通过。

## 专项记录

- [T060 依赖计划](T060-rebuild-dependency-plan.md)、[隔离 CI 计划](T060-isolated-ci-plan-2026-11-04.md)：区分方案与实际执行。
- [联网准备子进程修正](T060-preparation-bootstrap-2026-11-05.md)：源码修正与聚焦 / 整合回归边界。
- [浏览器证据计数](T060-browser-evidence-counts-2026-11-04.md)：区分实际执行、跳过、未运行和重试。
- [合成 WAL 恢复练习](synthetic-backup-recovery-2026-11-04.md)：仅覆盖固定临时样本，不是生产备份工具。
- [许可核验](licensing-2026-11-04.md)：结合[许可范围](../../LICENSE_SCOPE.md)与[第三方声明](../../THIRD_PARTY_NOTICES.md)阅读。

## 保存与更正

- 每份新报告记录任务 / 实验 ID、精确源码版本、实际环境、命令及退出码、PASS / FAIL / NOT_RUN、证据位置与未覆盖范围；可参考[地基报告模板](foundation-report-template.md)。
- 小型脱敏日志、获准保留的截图和清单可随报告保存；模型、数据集、数据库、浏览器凭据、原始敏感日志和运行环境不提交 Git。大产物仅记录允许公开的摘要与 SHA-256，不公开用户机器绝对路径或密钥。
- 原始实验记录按实验 ID 独立保存。修改结论追加更正并追溯旧版本，不覆盖原始数据；未知字段写“未记录”及其影响，不推测补齐。
- 测试替身、测试发现、静态检查、轻量测试、真实模型烟测和正式实验分别记录，不能互相替代。
