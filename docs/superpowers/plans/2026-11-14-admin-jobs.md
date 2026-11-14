# T070 管理员任务纵向切片 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 将既有管理员任务列表从 501 接通真实数据库，并在已有管理员工作台提供有界列表、任务查看与取消。

**Architecture:** 复用 `GET /admin/jobs` 的 Page[JobPublic]，以及现有单任务/日志/取消 API；没有迁移、新任务状态或依赖。用户管理与 capability 已存在，保留，不重建。

**Tech Stack:** 既有 FastAPI/SQLite、Vue/TypeScript/Vitest。

**Spec:** `docs/tasks/T070-final-validation.md`、`docs/scope.md`。用户明确委托自行决定、持续实现到交付，本计划为受托选择，不冒充用户逐项审批。

## Global Constraints

- 仅 admin 可跨项目列任务，普通用户仍服务器端 403；失效会话 401。
- page >= 1，1 <= page_size <= 100，稳定 created_at DESC,id DESC；仅现有公共 DTO，不暴露存储/进程身份或内部输入。
- 取消复用受控接口，不杀未知进程、不改任务状态机；只提供单任务取消，不批量破坏。
- 首次页和刷新读真实 API；翻页期间出现新任务允许现有 offset 语义，不伪装快照。
- 先做本切片，T070 全体仍未验收；正式实验、main 集成、用户机部署与交付材料另有闸门。

## Approaches

选择复用当前页面和既有 DTO：最小兼容增量。单独建立管理后台会重复身份与会话状态；增加监控/任务聚合 API 超出当前缺口，不采用。回退恢复 501 与隐藏新增面板即可，无数据迁移。

## Review Focus

- 普通用户/禁用管理员/过期会话不能列跨用户任务（API测试）。
- 同时间任务稳定分页、空页、过大参数拒绝（API测试）。
- 旧请求在卸载/账号变化后不能更新新界面（组件测试）。
- 重复取消只能一次在途，失败显示错误并允许恢复（组件测试）。
- 离线和分页失败不造成功，清楚标记旧数据；任务详情切换忽略旧响应（组件测试）。

## Task 1: 后端真实分页

Files: `backend/app/main.py`, `backend/tests/test_admin_jobs.py`。
Consumes: require_actor/require_admin、job_public、SQLite jobs。Produces: 既有 Page[JobPublic]。
- [x] 新增真实临时库测试，断言管理员空列表和跨项目分页、稳定排序、普通用户/禁用会话拒绝、参数上限、只含公共字段。
- [x] 执行该文件，确认成功路径因 501 而失败。
- [x] 在现有鉴权事务中计数并有界读取，复用 job_public。
- [x] 重跑测试及身份/Worker回归，检查契约漂移。

## Task 2: 最小管理面板

Files: `web/src/components/AdminJobsPanel.vue`, `.test.ts`, `web/src/api.ts`, `web/src/App.vue`。
Consumes: adminApi.jobs、jobApi.detail/logs/cancel。Produces: 仅管理员可见、会话 keyed 面板。
- [x] 先写分页/离线恢复/重复取消/卸载晚响应与旧详情响应测试并观察失败。
- [x] 实现有界分页、显式刷新、选中任务详情与有界日志、现有取消请求；不添加 ML 路径。
- [x] 前端全套、build/typecheck，相关 App 集成用例与真实浏览器管理员流程。

## Task 3: 审查和交付

- [x] 更新过时任务索引/证据导航和新切片证据；T070 尚未完整 accepted。
- [x] 独立审查、全量回归、敏感内容检查；按精确树备份安全推送并验证 CI。
- [x] 原生源码绑定可能失效，不复制旧证明；部署前重新建立实际环境 probe。

## 执行记录

- 方案独立审查无架构阻塞；现有用户管理/项目/capability 复用。
- 后端 RED：2 例因 501 失败、1 例禁用会话拒绝通过；实现后定向身份/Worker 15 passed。第一次从仓库根执行遇 app import error，已改正确 backend cwd，不计 RED。
- UI RED：空面板 4 例失败；实现后 4 passed；App 门禁 RED 管理员缺面板失败，接入后全前端 136 passed，build/typecheck 通过。
- Ruling: 既有 App 测试中泛化 /jobs? mock 意外匹配新 /admin/jobs?，使 4 个旧测试失败；增加独立 admin fixture 分支，原旧断言未弱化。
- 全量后端与真实浏览器验证尚在执行，不能把候选称验收。

- 最终前端 139 passed，build/typecheck:e2e 通过；契约检查无漂移。审查补强了晚取消/卸载 resolve/500 行上限。
- 本地浏览器 6 failed / 0 passed，Chromium executable 缺失，cleanup passed；未宣称通过。
- Ruling: P 文档历史测试硬编码“仍关闭”，CI #45 已确认单项失败；更新为精确 P 证据和剩余范围约束（7 passed），不是删除验收门禁。

- 精确远端 a454218 / tree844dc4d 的 #46 全部普通 CI 成功；真实浏览器5执行5通过，1预期ML跳过。最终本地861后端通过/14跳过/42子测试，前端139通过。管理员任务切片完成，T070整体未完成。
