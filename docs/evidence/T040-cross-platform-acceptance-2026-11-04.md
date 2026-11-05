# T040 跨平台进程与浏览器验收

日期：2026-11-04 UTC。**accepted（已实测的 Linux/Windows 受管进程、数据集异步校验与 Linux 浏览器范围）**。不是完整平台交付，也不是所有主机/硬件故障已实测。

## 精确受测版本

- 源码提交：`a61321ce3247c6e33c6c5462085da56f1e194b52`。
- Git tree：`6658b1cc6198a545df5935c7935b0e3d98e33a24`。
- 分支：`feat/t040-worker-validation`；未由本轮合并或改写 main。
- [最终 CI 41800377942](https://github.com/TudouXiang/edgevision-training/actions/runs/41800377942)，两个 job 均 success。本文是随后文档提交，不把旧 CI 冒充文档提交的执行结果。

## 实际命令与结果

[Linux job 126474395094](https://github.com/TudouXiang/edgevision-training/actions/runs/41800377942/job/126474395094)：Ubuntu 24.04 runner image 20261025.353.1、Python 3.12.14、Node 24.22.1。

- `python scripts/dev.py check`：退出 0，pytest **105 passed**，Vitest **10 passed**，类型检查/生产构建/契约漂移检查通过。标准库重复入口不另计为独立测试。
- `.venv/bin/python tests/http_restart_probe.py`：退出 0，真实 API 换进程重启、独立 Worker 继续工作、最终树退出 passed。
- `python scripts/e2e.py ...`：退出 0，Chromium **4 discovered / 4 completed / passed**。Chrome for Testing 156.0.8078.4、Playwright chromium v1248。覆盖身份/管理员/项目隔离、375px 键盘布局、真实上传/不可变版本/归档拒绝，以及真实 Worker 的 ready/invalid、最终日志、预览和报告下载。

[Windows job 126474394895](https://github.com/TudouXiang/edgevision-training/actions/runs/41800377942/job/126474394895)：Windows Server 2022 runner image 20261025.346.1、Python 3.12.10。

- 原生解释器探针 `pytest tests/test_python_launch.py -q -s`：退出 0，**4 passed**。原 venv 启动器 PID 不等于解释器 PID；修正后的实际 PID、完整出生身份、venv 前缀/解释器和依赖均一致。
- `pytest tests/test_guardian_settle.py tests/test_worker_process.py tests/test_worker_api.py -q -s`：退出 0，**40 passed**，无跳过。其中 6 项是确定性 supervisor 决策测试，不冒充 OS 运行证据；其余包含真实根/子/孙、nested Job、GO 前后取消、Worker/guardian 强杀、缺回执阻塞、发布竞争、实际数据校验和授权接口。
- `tests/http_restart_probe.py`：退出 0，真实 Uvicorn 重启、独立 Worker 与完整树退出 passed。

这些跨平台测试有重叠，不应把平台测试数量相加当成不同的业务能力数量。

## 审查与失败历史

独立实现/只读审查已检查状态 CAS、出生身份、整树退出、不可变产物/数据库事务、日志边界、迟到 UI 请求及测试证据。审查修正和本地日志见 [候选审查](T040-change-review-2026-11-04.md)、[累计报告](T040-report.md)、[ADR 0009](../adr/0009-t040-managed-worker.md)。

- 41796272092：Windows 3.12.14 无官方 runner 二进制；旧浏览器归档测试使用不存在的数据集。分别固定 Windows 3.12.10、用真实上传夹具保留 409 断言。
- 41797084998：Linux 全绿；Windows 22 fail / 8 pass。CPython venv redirector 身份错配由官方实现和随后原生探针确认。使用官方 multiprocessing 的直接解释器方式，不放宽身份/receipt 检查。
- 41798554667：Windows 29 pass / 1 fail，容量超限一次被分类为 RUNNER_FAILED；该次具体回执字段未记录，**原因仍未确认**。
- 41799258901：Linux/Windows 全绿，容量 5 次回执均 completed/exit71/完整退出。不能据此宣称前次偶发错误根因已修复。
- 最终版本另按 Windows 官方 Job 计数语义增加非阻塞 250ms 自然收敛策略：取消/EOF 优先，零计数才证明退出，超时仍保守清理/失败。此为独立稳健修正，不重映射错误、不把超时当成功。最终对应 CI 全绿。

## 闸门与限制

A06/A08/A09 和 A12 的当前 dataset_check 范围已有真实闭环与故障证据。A10 已实测 API/Worker 进程退出与恢复、出生身份/未知回执安全阻塞；**完整主机重启、物理掉电和跨重启存储持久性未实测**，不把 A10 所有主机场景整体标 PASS。Windows 无可信 receipt 的主机重启仍停止领取，不伪造自动恢复。

真实磁盘耗尽、用户旧库迁移、实际 TLS、人工视觉复核、Windows 浏览器、ML 训练/ONNX/RKNN/NPU 仍 NOT_RUN。注入存储故障不等于物理磁盘耗尽。T050 前置仍要求可信资产、目标 ML 环境及适用许可方案核验；尚未选择项目 LICENSE，未声称训练或部署完成。
