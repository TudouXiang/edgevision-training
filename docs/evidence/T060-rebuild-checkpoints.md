# T060 重建检查点 · 2026-11-04 UTC

本文件只记录本轮重新实现之后的结果，不引用丢失候选的测试计数。当前仍是 E 源码候选，不是可验收的 ONNX 发布版；I/P 未开放。

## 新执行结果

- 整合源码 `8f5ac18ba3b75606452c34d0e83533da2cda5212`：在 backend/ 用项目 `.venv/bin/python -m pytest -q`，两项 native-policy opt-in 为空，216 passed、9 skipped、8 subtests passed。包括普通 Python 受管进程、API TestClient 和纯逻辑 mock；不包含原生模型运行。
- 同一整合源码前端：`npm test` 36 passed；`npm run build` 通过；`npm run test:e2e:list` 类型检查和发现通过（5 discovered、0 executed）。
- 首次额外契约命令误用系统 Python，因缺 argon2 退出 1；改为项目解释器 `backend/.venv/bin/python scripts/export_contract.py --check` 后通过，没有安装系统依赖。
- 前端独立审查发现失败任务“新任务重试”在结果不确定时可更换幂等键、重复排队。`c1f6ba3647e76d14d0e7b547443a6e0b73906ad2` 改为按原失败任务持久保存替代尝试键，新增丢 POST/详情读取失败/重新挂载回归。38 项 Vitest 与构建通过，独立静态复审确认原问题解决。
- 隔离 CI 整合后，旧“永远 false”断言与新“仅显式 dispatch 且默认 false”契约不符；更新断言并验证普通 jobs 清空 native-policy opt-in。`4052980` 对应的 CI/privacy/installer 轻量组合 122 passed。最初从仓库根目录直接调用 pytest 因缺 app 导入路径收集失败；按 backend/ 标准入口重跑。

## 审查与待办

- 后端审查要求避免在 SQLite 写事务内散列大型数据集，正在修正并补轻量并发测试。
- 隔离 CI 已修正输入冻结、未知超时结果、SIGTERM 清理、共享清理预算、匿名参数错误；复审指出晚期报告/临时目录清理失败应保留已知阶段结果，正在修正。独立脚本也须明确检查 GitHub-hosted runner 前置上下文。
- 完整最终整合回归、修正后的独立审查与远端实际 CI 仍待完成，不把组件通过当作最终组合通过。

## 备份和隐私边界

每个源码阶段有独立本地 Git 提交，源码补丁与可独立恢复的完整 Git bundle 持久保存并保留版本。备份只包含仓库源码、测试、文档、配置和依赖锁；不加入模型、图片、数据集、运行数据库、私人原始日志。普通 push/PR 不触发真实 ML，显式隔离运行也尚未启动。

真实 ONNX/ORT、容器网络隔离、ML HTTP/浏览器和 Windows 新增 E 验证：**NOT_RUN**。官方 wheel 的版本/摘要核对不是实际安装或运行证据；mock 图对象测试不是 protobuf/ORT 兼容证明。

## 静态审查收口

- 后端修正 `7dd74a0`：只在读快照期间做完整文件/运行时校验；短写事务重查来源行、作业绑定、授权与状态后执行 CAS。独立静态复审接受。随后 `43ace06` 的晚期依赖/来源消失规范化 409 也经独立静态复审确认未发现回归。
- 前端 `c1f6ba3`：原失败任务的替代尝试键跨重试及重新挂载不变；独立静态复审接受。保持普通表单的已接收任务保护。
- 隔离 CI 完整组合 `993a59d`：独立静态复审未发现阻断；输入冻结、停止态检查、匿名输出、未知结果与取消清理、配套锁/安装器/HTTP/policy/browser 参数对齐。随后按复审精度建议增加工作流源 SHA 与候选 SHA 等值检查（`e8004c9`）；这是源码检查，不是证明 Docker/隔离/模型执行成功。
- 已执行的中间标准整合命令 `python scripts/dev.py check`：从 `993a59d` 启动，353 passed、9 skipped；38 项前端、TypeScript/Vite 和契约一致性通过。运行期间新增的文档及独立 CI 小修正不包含在该后端计数中，因此对最终冻结源码另行重跑，不借用此计数代替最终验证。

## 最终冻结源码轻量回归

源码提交 `ddcea869fee95a7693bbe35be2f056be03a09a36` 上，清空 `EDGEVISION_ML_POLICY_ROOT` / `EDGEVISION_ONNX_POLICY_ROOT` 后运行标准 `python scripts/dev.py check`，**退出 0**：

- 6 项契约 unittest 与 11 项脚本 unittest 通过。
- 后端 **356 passed、9 skipped**（231.45 秒）。跳过项是 6 项明确 opt-in ONNX policy 和 3 项训练 policy，不借此声称原生策略已通过。
- 前端 **38 passed**，TypeScript/Vite 构建与生成契约漂移检查通过。
- 同源码 E2E 类型检查/发现：5 discovered、0 executed；脚本 AST 检查通过。
- 有现存 Starlette/Alembic 兼容提示和 ZIP 重名拒绝测试警告，无测试失败。未为消除提示擅自升级锁定依赖。

之后仅补充本文档与状态说明，不改变已检查的业务源码。真实 Windows 新 E、ONNX/ORT、容器隔离及 ML 浏览器仍 NOT_RUN。候选可进入授权范围内的源码发布审查与普通轻量/Windows CI；不得触发隔离 ML 或跳过 E 业务验收闸门。
