# T040 Worker 与真实异步校验候选报告

日期：2026-11-04 UTC。状态：**review_required**，T050 blocked。实现 Agent 是唯一写入者，未提交/推送/合并；父级负责独立审查与发布。T030 accepted 基线为 `efa3284b3462932e34e99701c4099b2887a928ee`，受测 T030 代码 `a9309e7` 与 CI 41786393552；本轮不复用旧浏览器结果当 T040 证据。

## 输入、边界与实现

全部数据为临时目录内生成的 8×8 合成 PNG/JPEG 和 YOLO ZIP，无用户数据、模型权重、Torch/Ultralytics、系统安装、付费资源或训练。Linux：6.18.57 x86_64/glibc 2.41、Python 3.12.14、FastAPI 0.141.1、Pydantic 2.13.5、SQLAlchemy 2.1.1、Alembic 1.20.0、pytest 9.1.1、Pillow 12.3.0、Node 24.22.1/npm 11.9.0。

- ADR 0009 先经架构审查放行，再实施 0003 加性迁移；0001/0002 不改。jobs.owner_id 保存真实提交 actor，授权只追溯 Project.owner_id/admin。
- FIFO/单槽/单实例、同事务幂等插入、唯一 CAS+status event、ready 不可变；取消/中断/基础设施失败 pending，内容错误 invalid。
- Worker→guardian→固定 gated runner。Linux subreaper/pidfd，Windows typed Job Object/STARTUPINFOEX atomic membership/suspended start。失去 Worker 控制管道即清理；receipt+guardian exit 才终态。
- 校验报告与 snapshot 一体发布，树退出后重验冻结输入与全部输出哈希；publication intent→同卷 rename→Dataset/Artifact/Job 条件事务。取消先赢不发布，崩溃不重建成功。
- owner-aware Job/log/metric/report API、Job-bound 高水位游标、捕获及分页边界；前端独立 JobPanel 支持提交/取消/最终日志/分页、ready 预览与报告下载、项目切换/退出中止迟到响应。
- 16 MiB 报告/协议上限可能先于 20000 条目触发，明确 OUTPUT_CAPACITY_LIMIT，Dataset 保持 pending，不误报数据错误。stdout 只允许固定脱敏消息，不泄露 traceback/服务端路径。

## 已执行检查点（不替代最后一次全量）

1. 首条真实临时 API upload→queued→独立 Worker/guardian/validator→ready/succeeded，命令 `backend/.venv/bin/python /tmp/edgevision-t040-smoke.py` 退出 0，真实报告 Artifact、2 张图片统计和 drain receipt。此一次性探针后来由持久化测试覆盖。
2. `cd backend && .venv/bin/python -m pytest tests/test_worker_api.py -q`：5 passed；真实 valid/invalid 报告/预览、幂等/管理员代发起/归属、游标并发。
3. 初次进程矩阵 **6 failed / 7 passed**：本宿主 `/proc/self/task/<tid>/children` 返回 FileNotFoundError，取消/恢复不能 drain；没有把失败改写成通过。修复为仅在接口缺失时平面扫描当前 ppid=self 的直接子进程，仍由同一主线程持 pidfd/reap，不使用多代陈旧图；权限拒绝不回退。测试夹具自带 45/60 秒边界，未用广泛 pkill。
4. 修复后 `... pytest tests/test_worker_process.py tests/test_worker_api.py -q`：18 passed，34.05 秒。随后新增 GO/commit、恢复日志、rename/cancel、存储失败和损坏 receipt，单独进程矩阵 18 passed，34.27 秒。
5. `python scripts/dev.py check`：一次完整检查 83 backend passed、6 frontend passed、标准库 6+9、生产构建/契约通过。随后新增前端生命周期测试单跑 9 passed、构建通过。最后一次结果见下节，不拼接作为最终全量。
6. `cd backend && .venv/bin/python tests/http_restart_probe.py`：退出 0，`http_api_restart=passed independent_worker=passed tree_exit=passed`。真正启动、认证读取、终止并换 PID 重启 Uvicorn；同一个独立 Worker/孙进程继续执行，随后取消并核对树退出。普通 TestClient 重建用例只记 lifespan，不冒充进程重启。
7. `cd web && npm run test:e2e -- --list`：退出 0，发现 4 场景、完成 0，browser NOT_RUN。没有重试此宿主受限 Chromium。

## 最终统一检查

候选源码已冻结供只读审查，未提交/推送。源文件清单与逐文件 SHA 在 `T040-source-fingerprint-2026-11-04.json`，67 个源代码/配置/锁文件的聚合 SHA-256 为 `7765a67aa988e39a018133e87b600e43f5459f13c6b75b23ee90f73dd711c8ff`（算法/范围写在 JSON 中，文档与运行产物不纳入代码指纹）。

- `python scripts/dev.py check > docs/evidence/T040-local-check-2026-11-04.txt 2>&1`：退出 **0**。标准库 unittest 6+11 项，pytest **90 passed**（50.30 秒，无跳过）、Vitest **10 passed**、Vue/TypeScript 类型检查及 Vite 生产构建通过、实时 OpenAPI/TS 无漂移。日志 SHA-256：`bfabbda1a60ec86c28e5be64313db9824e08904ce5e5e601ec25bdc4f8c07212`。
- `cd backend && .venv/bin/python tests/http_restart_probe.py`：最终候选重新执行退出 **0**；原始安全日志 `T040-http-restart-2026-11-04.txt`，确实换 PID 重启 Uvicorn、保持同一个 Worker 运行并最终取消整树。
- `python scripts/e2e.py --list --report-dir /tmp/edgevision-t040-discovery-report`：退出 **0**，真实临时 Uvicorn/Worker/Vite 编排与最终删除清理通过，发现4、完成0、browser NOT_RUN，安全结果复制为 `T040-browser-discovery-2026-11-04.json`。没有本地 Chromium 执行。
- `UV_CACHE_DIR=/tmp/edgevision-uv-cache uv lock --project backend --check --offline`、`git diff --check`：退出 **0**，未安装依赖。

Windows/真实 Chromium 必须由发布后精确提交的 CI 补证，当前均 **NOT_RUN**。Windows CI 对应共同进程矩阵，并额外实际执行 nested Job 场景；不是用全部跳过变绿。最终整机重启仍不在托管 job 能力内。

最后完整检查后仅补 Worker 控制管道退出竞态：STOP/GO 遇 BrokenPipe 继续核对 drain receipt，不将管道断开等同退出证明。新增回归单跑 **1 passed / 22 deselected**，见 `T040-control-race-2026-11-04.txt`；首次从仓库根运行因 app 导入路径错误而 collection failed，改在 backend 目录重跑通过。该最后微调尚待父级独立全量 91 项检查，不能将前述 90 项日志当作最终源码全量结果。此前 88/10 日志保存在 `T040-local-check-pre-final-review-2026-11-04.txt`。最近审查还补齐独立服务清理、非 ASCII /proc comm 解析、Windows guardian 丢失时清理前整树退出断言。HTTP 重启与 discovery 日志为该微调前的实际执行证据。

## 故障与验收对应

- A08：并发 API 同键/不同参数、终态重放、同 Dataset 活动任务复用、竞领 FIFO、第二 Worker 真实文件锁。
- A09：queued 不启动、GO 前取消、运行树/孙进程/setsid/TERM 抵抗、取消赢完成、rename 后取消、终态事件唯一。成功先提交的取消返回成功原态。
- A10：claimed 未启动可中断；spawning 无证据阻塞；真实 Worker 强杀前/后 GO 的 EOF 清理及重启 interrupted；guardian 强杀缺 receipt 阻塞；未知/复用出生身份不发信号；真实 Uvicorn 重启。changed boot 分支只有逻辑测试，不是硬件重启。
- A12：退出 0 缺输出/损坏输出不能成功；输出洪泛仍 drain；发布 rename 后/DB commit 后强杀；存储失败和报告容量失败不伪造 invalid；receipt 畸形 fail closed；有界下载重新核对 hash。
- A06/A07：复用 T030 全量负向核心与不可变输入；真实 valid/invalid 新增异步证据。训练输入/模型不属于 T040。

## 仍未执行/不声称

Windows 真实 Job Object、nested Job/初始 suspended cancellation 与 Windows 故障矩阵已加入 CI，尚未运行；Linux Chromium 新场景也待 CI。完整主机重启、硬件掉电、真实磁盘耗尽、人工视觉/TLS、用户旧库、ML/ONNX/RKNN/NPU 均未执行。存储故障注入不等于物理磁盘耗尽。Windows 无可信 boot ID 且无 receipt 时停领，是明确安全限制，不是假恢复成功。

本报告不是最终 accept。最终需独立只读审查、对应候选提交的 Linux/Windows CI 和真实浏览器结果，再由父级决定 T040 闸门。

最终 HTTP 重启日志 SHA-256：`27f483b5ad15357a8808821fe48940443a8b9605839c51e2325b3f9b9244a361`。

## 父级最终候选独立核验

最终指纹不变，独立全量 91 backend / 10 frontend、构建/契约、真实 HTTP 重启与四场景 discovery 均通过；discovery 完成 0，浏览器仍 NOT_RUN。具体命令、退出码及日志见 [独立审查](T040-change-review-2026-11-04.md)。此处不接受 T040，仍等待候选提交的 Linux/Windows CI。


## 首次 CI 与 Windows 运行时修正

公开候选提交 `bf6b84922400e1561cdfc613f5eac941d420cba6` 的 [首次 CI 41796272092](https://github.com/TudouXiang/edgevision-training/actions/runs/41796272092) 中，[Windows job 126461007744](https://github.com/TudouXiang/edgevision-training/actions/runs/41796272092/job/126461007744) 在 setup-python 阶段失败：Windows 2022/x64 没有 Python 3.12.14 构建。进程/API 矩阵未运行，不记为测试失败或测试通过。

根据 [actions/python-versions 官方版本清单](https://github.com/actions/python-versions/blob/main/versions-manifest.json) 中提供的 Windows x64 Python 3.12.10，本次只将 Windows job 固定为 3.12.10，Linux 仍为 3.12.14；没有版本回退逻辑或跳过失败。Windows summary 改为展示矩阵步骤的真实 outcome，配置范围不再冒充已执行证据。

这是工作流及证据文档的后续调整，没有业务源码变化。此前源指纹 `7765a67aa988e39a018133e87b600e43f5459f13c6b75b23ee90f73dd711c8ff` 对应原候选，不宣称覆盖本次改动后的工作流。待父级发布新提交并重新取得 Windows 实际运行证据。


## 首次 Linux CI 与归档浏览器夹具修正

同次 CI 41796272092 的 Linux 实际结果为后端 91 / 前端 10、构建/契约及真实 HTTP 重启通过；Chromium 为 **3 passed / 1 failed**，新增 T040 Worker 全链路浏览器场景已通过。失败的是旧 T020 归档测试使用不存在的 Dataset UUID，资源核验先返回 404，未到达期望的 `409 PROJECT_ARCHIVED` 分支。不能将这次部分浏览器通过记成全套通过。

本次仅修正浏览器夹具：在项目归档前用现有已认证页面上传合成 ZIP，确认 Dataset 属于该项目且为 pending；归档后对这个真实 Dataset 使用新幂等键提交，继续严格断言 `409 PROJECT_ARCHIVED`。不改变生产错误优先级或弱化为 404，不输出凭据。重新执行仅做 TypeScript 与四场景发现，真实 Chromium 仍待下一次 CI。

本次有限回归：`npm --prefix web run test:e2e:list` 退出 0，TypeScript 通过、发现 4 / 完成 0、browser NOT_RUN；`cd backend && .venv/bin/python -m pytest tests/test_worker_api.py -k concurrent_submission_single_job_key_conflict_and_actor_authority -q` 为 1 passed / 5 deselected；`git diff --check` 通过。这些不替代待运行的完整 Chromium 验证。


## Windows 首次真实矩阵与 redirector 修正

提交 `2c194bb4cbc68b292a034243a30007b6d12c8d7d` 的 [CI 41797084998 / Windows job 126463600990](https://github.com/TudouXiang/edgevision-training/actions/runs/41797084998/job/126463600990) 已真正执行矩阵，结果 **22 failed / 8 passed**，不是 setup 失败或跳过。pre-GO 测试已到 identity barrier，Worker 强杀前 GO 用例已有 drain receipt/guardian exit 但被严格身份匹配拒绝；大多数执行标记超时。Linux 同提交全套通过，不能抵消 Windows 失败。

根因依据为 [CPython 3.12.10 Windows launcher](https://github.com/python/cpython/blob/v3.12.10/PC/launcher.c) 通过 CreateProcessW 启动并等待另一个解释器，以及 [stdlib multiprocessing 的明确修正](https://github.com/python/cpython/blob/v3.12.10/Lib/multiprocessing/popen_spawn_win32.py#L55-L62)。当前 Worker 错把 redirector 的 Popen PID 与实际 guardian 自报出生身份比较。采用官方 direct-base + 子环境 venv 标记方式，保持原有出生身份/receipt 校验；完整原生确认仍由下一次 Windows CI 的 fail-fast 探针和未削弱矩阵完成。未伪造 Windows 本地通过。

本次修正的 Linux 有限回归：`cd backend && .venv/bin/python -m pytest tests/test_python_launch.py tests/test_worker_process.py tests/test_worker_api.py -q -s` 为 **33 passed / 0 skipped**（39.98 秒），日志 `T040-python-launch-local-2026-11-04.txt`；安全探针显示 PID/出生身份/venv/依赖全部匹配，windows=false，不冒充 Windows 实验。`tests/http_restart_probe.py` 退出 0、真实 API 重启/独立 Worker/整树退出通过，日志 `T040-python-launch-http-2026-11-04.txt`。脚本单元测试改在 backend 正确目录执行为 11 passed；先从仓库根执行曾因 app 导入路径缺失报 1 error，未当作通过。工作流 YAML 和原生探针先于矩阵的顺序断言、`git diff --check` 通过。此次候选仍待 Windows 原生 CI；此前代码指纹只描述原始候选，不覆盖本次兼容性修正。


## Windows direct-interpreter 实测与剩余诊断

[CI 41798554667 / Windows job 126468410873](https://github.com/TudouXiang/edgevision-training/actions/runs/41798554667/job/126468410873) 的原生探针 **4 passed**，`raw_pid_matches=false`，direct PID/出生身份/venv/依赖均为 true，实际证实并修复 redirector 身份根因。完整进程/API 矩阵推进为 **29 passed / 1 failed**：仅输出容量故障预期 `OUTPUT_CAPACITY_LIMIT` 却得到 `RUNNER_FAILED`。树清理、取消、恢复、nested Job 等其他用例通过不抵消此错误分类失败；HTTP 重启后续步骤因矩阵失败未执行。

本次仅为该断言加入 receipt 的五项白名单诊断：reason、exit_code、logs_complete、started、tree_exited。不输出路径、身份、环境或用户数据，不改变生产行为或预期值。Windows Job ActiveProcesses 在退出且所有引用释放后才递减（[Microsoft 官方说明](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_accounting_information)），但当前失败尚无 receipt 字段，不能把计数滞后假设写成已证实根因。待下一次精确 CI 取证。

诊断调整本地仅执行 `cd backend && .venv/bin/python -m pytest tests/test_worker_process.py -k output_capacity_failure_remains_pending -q`：Linux 1 passed / 22 deselected（1.75 秒）；`git diff --check` 通过，不视为 Windows 故障已修复。

诊断补充：容量场景仅重复五次，Windows 矩阵 `-s` 输出白名单 receipt 字段；无环境/路径/标识或用户内容。保留完整进程矩阵和严格错误码断言，不将偶然通过解释为缺陷已修复。


## Windows 诊断全绿与独立计数稳健性修正

提交 `ec83268` 的 [CI 41799258901](https://github.com/TudouXiang/edgevision-training/actions/runs/41799258901) 已全部通过：Linux 后端 99 / 前端 10 / 真实 Chromium 4 项及真实 HTTP 重启，Windows 原生探针 4 / 进程矩阵 34 项及真实 HTTP 重启。五次容量场景都记录 reason=completed、exit_code=71、logs_complete=true。此前唯一 RUNNER_FAILED 的 receipt 详情缺失，故根因依旧未确认；不能把后续通过或以下修正写成已经复现并修复那次失败。

经独立审查批准，额外完成 Windows Job accounting 的最小稳健性修正：root exit 后非阻塞 250ms 自然收敛，每 poll 继续处理 STOP/EOF；归零直接完成、不人为 Terminate；过窗非零仍保守失败清理，持续非零绝不生成 receipt。Linux 与所有真实树/取消/恢复/错误码断言不变。新增 6 项确定性 supervisor 回归仅验证状态决策，不冒充 Windows 原生实验；新版本仍待精确提交 CI。

最后有界修正本地证据：`cd backend && .venv/bin/python -m pytest tests/test_guardian_settle.py tests/test_worker_process.py tests/test_worker_api.py -q -s` 退出 0，**39 passed / 0 skipped**（46.49 秒），日志 `T040-settle-local-2026-11-04.txt`。`tests/http_restart_probe.py` 退出 0、实际重启及树退出通过，日志 `T040-settle-http-2026-11-04.txt`。`git diff --check` 通过。以上是 Linux 宿主及确定性决策回归；修正后的 Windows 原生矩阵与浏览器仍待新提交 CI，不挪用 ec83268 的全绿结果。
