# T030 独立验收：Linux 数据导入核心

日期：2026-11-04 UTC。结论：**T030 accepted（Linux 核心范围）**，T040 ready。完整异步数据校验仍由 T040 实现，不把 pending 当 ready。

## 精确版本与真实执行

- 受测提交：`a9309e7d9be279ca1143c1a49dd31d2fdfe085f5`。
- 受测树：`a72594989d065fb8aa76f6ca652c6e92efebb2a5`。
- [GitHub Actions 41786393552](https://github.com/TudouXiang/edgevision-training/actions/runs/41786393552)，job `126429393555`，结论 success。
- 环境：Ubuntu 24.04 托管 runner，Python 3.12.14，Node 24.22.1，Playwright 1.64.1，Chromium 156.0.8078.4 / revision 1248。
- 原始 job 日志：`2026-11-04T06:35:09.2731436Z browser_e2e browser=passed browser=passed discovered=3 completed=3`。
- 同一 job 的完整聚合：pytest 60 项通过（9.06 秒）、Vitest 6 项通过、基础 unittest、生产构建、生成契约无漂移。

真实浏览器执行两条 T020 身份/权限/项目/375px 键盘回归，以及一条 T030 真实上传、pending、同名新版本、刷新重读与归档禁止上传链路。后端隔离测试另覆盖纯校验、授权、不可变发布、最终会话复核、并发版本与失败清理。独立变更审查见 [审查记录](T030-change-review-2026-11-04.md)。

## 失败记录与修复

首轮提交 `29107984e7c6204072af08363662205fd24a496a` 的 [run 41785821044](https://github.com/TudouXiang/edgevision-training/actions/runs/41785821044) 整体失败：T030 场景通过，旧 T020 两条场景因全页文本定位同时匹配项目卡片和新增下拉选项而失败。后续仅将断言定位到项目卡片，并约束移动端 select 宽度；未删场景、未放宽权限或成功判定。当前成功 run 是全部三项重新执行，不拼接多轮结果。

## 验收边界

- A06：T030 受限接收和纯校验核心通过。HTTP 不解压/解码重型数据，不创建虚假任务。
- A07：T030 Dataset 不可变记录、源 ZIP 哈希与版本链通过；训练绑定尚属 T050。
- 现有 Dataset 查询、预览授权继续通过 A05 相关回归；ready 预览的集成测试数据只在隔离测试中构造，生产 ready 发布尚未实现。
- Windows 新功能、真实 TLS、人工视觉/截图检查、实际磁盘耗尽、多进程压力、硬件断电未执行。fsync/DB 失败注入不是实际磁盘耗尽或断电证据。
- Worker 串行领取、取消/进程树退出/崩溃恢复、真实 upload→ready/invalid、日志与报告下载均待 T040。
- ML、真实数据、训练、ONNX、RKNN/NPU 均未因本验收执行。

本次验收解除 T030 对 T040 的前置阻塞，不表示项目整体完成。文档验收提交不改变上述受测代码；其后 CI 结果单独核对。
