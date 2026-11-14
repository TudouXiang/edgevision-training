# T070 管理员任务切片候选

状态：review_required，非 T070 或全项目验收。前置 P 的限定验收版本和本切片分别记录，不把旧 probe 复制为新环境能力。

## 实现

- 既有 `/admin/jobs` 从 501 改为管理员真实全局列表；原 Page[JobPublic]、page/page_size 边界不变，同一鉴权事务内计数/读取，稳定时间与 ID 排序。无 schema 迁移。
- 复用既有 App 的用户管理、全项目和 capability，不增加新权限、监控系统或批量取消。
- 新 AdminJobsPanel 按会话 generation 重建，手动刷新、有界页与日志；详情 revision 防过期响应；取消复用现有受管接口，cancelling 仅表示请求接收，必须再读终态。
- 新真实浏览器用例创建隔离普通用户、上传合成数据、执行真实 Worker；管理员跨项目查看详情/日志，普通用户列表 403；刷新与窄屏验证。用例存在不等于已经通过。

## 检查证据

- 定向后端身份/Worker/新接口：15 passed。
- 新后端 RED：2 个成功路径因 501 失败；禁用会话拒绝通过。实现后转绿。
- 前端最终完整 139 passed；build、typecheck:e2e 通过。面板最初空实现 4 例失败，接入前 App 管理员门禁失败，完成后转绿。
- 新补强：晚取消响应切换详情、卸载后 resolve、日志 600→保留500、实际 HTTP wrapper 的凭据与 AbortSignal。
- `scripts/export_contract.py --check`：匹配，无公共类型漂移。
- 全量后端首次仍在执行，旧文档断言已单独复现并修正，最终以精确 CI 为准。
- 本地普通浏览器：6 discovered / 6 failed / 0 passed，cleanup passed。固定 Playwright Chromium executable 不存在；不算 UI 执行通过。留待有浏览器的 CI。
- 独立审查未发现阻塞性权限/执行缺陷，仍要求全量和浏览器通过。

## 历史文档回归修正

P 文档备份 `f0a97b93d62b665151618a9447de1534080b3ecc` 的 #45 / 43633778327：Windows success，checks failure；精确失败是 `test_current_image_acceptance_stays_scoped_and_keeps_package_pending` 仍断言 README 中 P 关闭。857 passed、1 failed、14 skipped。这不改变 #44 的模型实测通过事实。
本候选把文档测试更新为精确版本/树/运行绑定、每产物未执行说明、不含解释器/wheels、每环境新 probe 及 T070/全项目未验收断言；该文档文件 7 passed。没有删除作用域保护或把历史失败改成成功。

## 完整交付尚缺

1. 本切片精确 CI、实际浏览器验收以及 A01–A16 当前版逐项核对。
2. 基础实验对比界面与既有真实指标的需求映射；正式实验冻结数据、划分、预处理/阈值/计时口径和预算后执行；合成烟测不能替代准确率报告。
3. 干净环境复现与用户目标机部署；每环境的新 probe、可运行入口和用户验收。尚无本版本 PEC003909/XIAOHU 部署证据。
4. 操作/部署说明、演示脚本、架构/模块说明、完整测试报告、论文素材索引；学校正式题名/硬件硬性要求不能凭空补写。
5. 安全集成至 main 或明确最终交付分支，核对其他贡献、CI 与回退。当前功能分支推送不代表 main 已交付。
