# Codex 接手记录 · Windows 源码快照（2026-09-28）

> 2026-09-29 更新：在隔离环境重新完成 A01–A04 补证，修复状态守卫漏项并通过独立 change-review；T010 **accepted**，T020 **ready、未领取**。当前判定以 [`docs/status.md`](status.md)、[`T010 复核报告`](evidence/T010-review-2026-09-29.md) 和 [`独立审查`](evidence/T010-change-review-2026-09-29.md) 为准。以下 2026-09-28 的 PASS 候选和 blocked 描述是接手时的历史快照。

## 工作区与 Git 来源

当前工作区是 `D:\WorkSpace\edgevision-foundation`。接手时这里有 EdgeVision 源码、既有 `backend/uv.lock` 和未纳入版本控制的项目环境，但**没有 `.git` 及网页 Work 交接所述的本文件**。因此不能验证原 `d5eade0` 提交、原来的未提交 diff 或远端/未推送状态。`scripts/install_deps.py`、编辑前的 `scripts/dev.py` 与交接指纹吻合；这只能证明两个文件一致，不能还原历史。

用户选择以此源码快照建立新的 Git 历史，并授权推送至公开仓库 `git@github.com:TudouXiang/edgevision-training.git`。新 `main` 根提交为 `bcf0642bc7dcc7e2ab7da3b4dd7d9f21e7710bd6`，说明原历史不可验证。Git 发布结果以实际 `git status`、`git log` 和远端引用为准；不要把新根提交写成原项目历史的后继。`reference/edgevision-studio-frontend.zip` 只是含模拟数据的旧演示原型，不是正式 API/测试依据。

## 当前可执行状态

Windows 本机已有项目 `.venv`、`node_modules`；依赖预检、锁文件离线检查、项目测试、Vue 构建和契约检查通过，**本轮没有重新安装依赖**。`contracts/openapi.json` 与 `contracts/generated/openapi.ts` 已由 FastAPI 生成，前端健康页引用生成类型。默认 `data/platform.db` 是 `0002_foundation` 且业务表为空，本轮没有用它做写入试验；所有迁移和服务探测均使用独立临时 `PLATFORM_DATA_ROOT`。默认 8000/5173 已有其他进程，Windows 实测使用 18000/15173；开发入口可通过 `EDGEVISION_DEV_API_PORT`、`EDGEVISION_DEV_WEB_PORT` 改端口。

A01–A04 在本机隔离环境为 **PASS 候选**，完整命令、退出码、迁移数据指纹、HTTP/浏览器观察和未执行项见 `docs/evidence/T010-windows-2026-09-28.md`。真实旧用户库副本不可得，只验证了带代表性记录的 `0001` 样本及其一致性副本。Windows 占位 Worker 的单实例、失败与遗留停领路径已测；真实任务的进程树取消、重启和恢复属 T040。Torch、Ultralytics、ONNX、RKNN、训练/推理及 NPU 实机均未执行。

## 下一步闸门

按 `AGENTS.md` 顺序读 `docs/status.md`、`docs/scope.md`、`docs/architecture.md`、`docs/contracts.md`，再读任务单、`docs/acceptance.md` 和本次证据。2026-09-29 独立审查已将 T010 放行为 `accepted`，T020 现为 `ready`，但本轮没有领取或实现。范围、公共接口、任务状态、存储或技术栈变化先走 `arch-spec`；逐项开发、改动审查和实验证据分别按仓库 Skill 手动核对。

对真实旧库升级时先停 API/Worker、做一致性备份，在副本试迁移；不得在唯一副本试错。默认数据、用户正在使用的 8000/5173 进程和未取得许可的模型/数据均不因接手而自动处理。
