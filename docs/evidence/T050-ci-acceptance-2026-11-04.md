# T050 Linux CPU 训练闭环验收

日期：2026-11-04 UTC。结论：**accepted，仅限以下实际验证范围**。

## 精确代码与远端结果

- 功能分支：`feat/t050-training-lifecycle`。
- 源码提交：`c398426b2ba9369d769479ca3fcb7c09600f7bab`。
- 完整 tree：`fec4e3bdeed210e518c0ad7612668bea24accd13`，与本地最终独立聚合测试的 tree 完全相同。
- [GitHub Actions 41812272849](https://github.com/TudouXiang/edgevision-training/actions/runs/41812272849)：completed / success，三个 job 全部通过。
- `main` 未合并或改写；此次代码发布不包含权重、图片、数据库或用户数据。

## 实际 CI 执行

1. [Linux 轻量检查](https://github.com/TudouXiang/edgevision-training/actions/runs/41812272849/job/126514194222)：143 pytest passed / 3 optional ML skipped，15 前端测试，构建与生成契约一致性通过；真实 HTTP API 重启、独立 Worker 与进程树退出通过。既有身份、项目、数据与 Worker 浏览器回归通过，新增 ML 场景在此轻量环境明确跳过。
2. [Linux 实际训练](https://github.com/TudouXiang/edgevision-training/actions/runs/41812272849/job/126514193714)：独立安装完整 hash lock，取得并核对固定官方基础权重，真实 Uvicorn → Worker 单轮 CPU 训练与双 PT 下载通过；3 项实际 ML 策略失败测试通过。Chromium 的 5 项场景全部执行通过，包括真实训练、最终指标、两个模型下载、刷新恢复和窄屏检查。
3. [Windows 进程回归](https://github.com/TudouXiang/edgevision-training/actions/runs/41812272849/job/126514193408)：4 项原生解释器身份测试、40 项既有进程/API/决策矩阵、真实 HTTP 重启通过。此 job 不安装 ML，不能据此声称 Windows 训练已通过。

独立源码审查发现并修复了探针与孤儿任务重叠、嵌套标签路径、下载断线句柄泄漏、取消响应覆盖其他选择、详情失败丢失幂等键、终态轮询退避和分页旧响应问题。最终修复的测试与本地真实 HTTP 原始结果见 [实现报告](T050-report.md)；不把测试替身的故障注入说成实际长训练。

## A11/A12 的适用边界

已验证固定 YOLO11n、可信平台数据快照、白名单参数、Linux CPU、真实轮次指标、净化后的安全 PT 重载、完整产物束登记与鉴权下载。合成矩形图片只用于确定性管线验证；指标不是泛化精度证明，也不是正式毕设实验结果。生产默认参数在本地最终一轮小样本任务中实际完成 1 次 SGD 更新；早期独立 nbs=1 烟测的 4 次更新是不同配置，不混用证据。

缺产物、损坏、未知类、参数漂移、非有限张量、取消、Worker 丢失、指标损坏、发布事务回滚及断线下载均有相应本地/CI 测试。物理磁盘耗尽、整机掉电、长任务资源压力、真实用户旧库、实际 TLS、人工视觉、Windows ML、CUDA、ONNX/ORT、RKNN/NPU 与正式精度实验 **未执行**。Python 审计不是完整操作系统网络隔离。

T050 accepted 不等于完整平台交付。T060 可进入受限前检与架构设计；真实 ONNX 导出、数值校验、推理与独立部署包仍须分别实施、测试、审查。AGPL 原创许可不替代第三方资产权利，COCO8 不进入公开仓库或发行包。
