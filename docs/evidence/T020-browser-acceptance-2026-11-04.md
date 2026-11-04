# T020 真实浏览器补证与独立验收 · 2026-11-04 UTC

结论：**accept**。T020 身份与项目纵向切片在 Linux CI 范围内 accepted；T030 ready、尚未领取。此结论来自先前独立代码/安全审查、当前完整自动检查与真实 Chromium 操作，不由 CI 工作流自行修改闸门。

## 可核验来源

- 已测试源码提交：`cc2e66043473b9d3f432319fab41130cab3f2270`。
- Git tree：`d9e0a643b0e4f0902dcce18dbb5def74546a7148`。
- [GitHub Actions run 41779814303](https://github.com/TudouXiang/edgevision-training/actions/runs/41779814303)，事件 push，分支 `feat/t020-auth-projects`，结果 success。
- [checks job 126408548245](https://github.com/TudouXiang/edgevision-training/actions/runs/41779814303/job/126408548245)，所有测试步骤 success，失败附件步骤 skipped。
- 执行时间：2026-11-04 05:32:01–05:33:03 UTC。Ubuntu 24.04.5，runner 2.338.2，镜像 ubuntu-24.04 / 20261025.353.1，Python 3.12.14，Node 24.22.1，npm 11.19.1，Playwright 1.64.1，Chromium 156.0.8078.4（revision 1248）。

原始日志关键行：

```
2026-11-04T05:32:34.0134135Z ======================= 26 passed, 16 warnings in 7.48s ========================
2026-11-04T05:32:41.3167353Z contract artifacts match live FastAPI/Pydantic schema
2026-11-04T05:33:02.9526620Z browser_e2e browser=passed browser=passed discovered=2 completed=2
```

完整日志可从上述 job 查看；只摘录不含凭据、Cookie 或数据库内容的结果。历史首次配置失败 run 41779527773 保留，原因与修正见 browser-ci-source 报告；不能将首次失败当成浏览器运行。

## 实际通过的范围

- 新环境锁定依赖安装；unittest 6+9、pytest 26、Vitest 4、Vue 类型/构建、契约漂移全部通过。
- 测试包装器建立独立临时数据库、运行正式 Alembic 迁移、显式创建随机测试管理员，连接真实 Uvicorn/Vite 同源代理；测试不模拟业务 API。
- 浏览器用例 1：错误/正确登录，刷新会话，管理员创建/禁用/重启用账号，重复用户名拒绝，项目创建重复触发守卫、取消编辑/保存/刷新、归档保留与重复归档、新任务拒绝，普通用户管理 API 403/他人项目 404，禁用撤销、改密轮换 session/CSRF 和撤销另一浏览器会话，退出刷新与新旧密码验证。
- 浏览器用例 2：375px 真实 Chromium 视口；Tab/Enter 登录，Enter 创建长名称项目，检查无横向溢出，Back/Forward 与键盘退出。
- 独立审查核对真实用例无 skip、无 API mock，默认不是 --list，成功日志明确 discovered=2/completed=2。原有安全发现已修复，参见 T020-change-review 报告。

## 闸门判定与保留边界

T020 任务要求的现有资源身份/项目与最小浏览器闭环已经有实际证据；A05 对当前已有资源通过。T030 只能据此领取自己的受限数据导入/校验任务，不自动放行 T040 或后续训练。

以下仍**未执行**，不从本次结果推断：Windows 上 T020 新功能、真实 TLS 部署、人工视觉/截图审美验收、多进程并发压力，以及尚未实现的完整 Dataset/Job/Artifact 业务访问。375px 结论是自动化交互/溢出检查，不是所有尺寸或所有浏览器视觉验收。权限前置守卫不等于未来上传/下载功能已实现。数据集、训练、ONNX、RKNN/NPU 与最终 A15 全链路仍未验收。

本记录的提交仅更新文档/闸门，测试结果对应上方明确的源码提交；后续变更必须重跑相关 CI。main 未合并，生产用户数据库未触碰。
