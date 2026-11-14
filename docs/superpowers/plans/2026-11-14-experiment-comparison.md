# T070 基础实验对比 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为既有 V1 必须交付的“基础实验对比”提供同项目两个真实训练任务的参数、来源与最终指标对照，不伪造实验或排名。

**Architecture:** Vue 独立 ExperimentComparisonPanel，复用 jobApi.list/detail/metrics 与生成的 Job/Metric 契约，无新后端端点、迁移或依赖。仅手动读取，按项目/会话 key 隔离。

**Tech Stack:** 当前 Vue/TypeScript/Vitest 与既有真实 API。

**Spec:** `docs/scope.md` 必须交付能力、`docs/tasks/T070-final-validation.md`、`.agents/skills/experiment-evidence/SKILL.md`。

## Global Constraints

- 不启动训练，不修改任务，不把 failed/interrupted 的部分指标称最终完成指标。
- 一次至多对比 2 个不同 train 任务，必须同当前项目；读取详情重新检查 kind/project/state。
- 成功任务才能列“最终指标”，每个最多读 4 页 * 500 项，未 eof 或 cursor 不前进须显示读取不完整，不宣称完整对比。
- 按各指标最大 seq/epoch 选择最后实际观测值；缺失显示“未提供”，不能写 0；数值是训练输出，不冒充独立测试集报告。
- 显示 dataset ID/version/snapshot、基础权重、imgsz、epochs、seed、batch、learning_rate、runtime/code 摘要。数据来源/环境不同明确提示不宜直接排名；不做默认优胜判定。
- 有界列表分页、明确刷新；网络失败、卸载/切换项目/更换选择晚响应均不污染新结果。
- 沿用原有只读 API 权限；不扩大训练模型、硬件、正式实验预算或远程部署。

## Approaches

选择两个任务的参数/来源/指标文本对照，最小且可解释。重构全训练页会扰动已验收提交与恢复流程；另建实验数据库重复现有 Job，不采用。现有单任务曲线保留，不造不同刻度的跨任务叠图。回退移除面板，无数据迁移。

## Review Focus

- 切换选择后旧 metrics response 到达（组件测试）。
- 指标多页、不前进游标、超预算而无 eof（组件测试）。
- 不同数据/基础权重/环境与缺失指标不可误排名（组件测试）。
- 同 ID、非 train、跨项目或终态失败详情拒绝最终比较（组件测试）。
- 普通用户仅能比较自己的项目；管理员遵循已有权限（现有服务器权限回归+App门禁集成）。

## Tasks

- [ ] 先写组件 RED：真实两任务指标/参数显示、missing非0、来源差异警告、多页eof、旧响应丢弃、网络错误与恢复、无效详情拒绝。
- [ ] 最小面板实现，仅原 API；任务页列表可翻页，选中 ID 不因翻页偷偷变更。
- [ ] App 接入前写集成 RED；按 session/project key 装卸，与既有 TrainingPanel 相邻。
- [ ] 全前端/构建/契约检查、后端全套、独立审查与真实 CI 浏览器覆盖；未实测路径如实标 NOT_RUN。
- [ ] 留档、安全分支备份，检查精确 CI；与正式实验报告分开。

## 前置状态

本方案尚未实施。管理员任务 `a45421849c4b888be4ee01137c75de113b05d746` 已完成 #46 普通回归与真实浏览器核验；本方案可以继续，不视为 T070 整体已完成。
