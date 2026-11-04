# T050 固定 YOLO11n 训练闭环 · review_required

日期：2026-11-04 UTC。起点：T040 accepted 3795759；前置许可与设计见 ADR 0010/0011。
本报告不把本地实现/烟测等同全部平台验收。最终 CI、Windows 训练、CUDA、ONNX、RKNN、精度实验未完成。

## 已实现范围

- 同项目 ready Dataset、不可变完整报告/文件清单、参数与可信基础资产冻结；权限、归档、幂等和新任务 retry 来源。
- 同一联合解释器的显式受管 CPU 探针；API 不 import Torch，不接受任意模型路径或解释器。
- GO 后固定适配器：独立复制、规范 YAML、真实样本/标签一致性、安全加载与网络/子进程审计。
- 固定 SGD，有效参数可追溯；非有限 loss/live/EMA/FP16、OOM 隐式减 batch、epoch 重放和未知 checkpoint 类失败关闭。
- 独立指标 journal、有界日志、最终指标读取、双 PT 最终净化/重载/哈希、取消 CAS 与完整束原子发布。
- typed provenance、鉴权同句柄下载、训练表单、真实曲线、分页/刷新/取消/新任务重试；生成 OpenAPI/TS。
- 沿用 0003_worker，无表迁移。未触及 main 或发布资产。

## 实际执行

1. 35 项新轻量测试 PASS：严格参数、权限/归档/ready、幂等重试、报告损坏、指标原子去重/尾部/坏绑定、
   双文件缺失/多余/损坏/取消/事务回滚、实际 train-kind 进程取消/Worker 丢失/坏指标 STOP+drain、
   探针歧义停领/活动 Job 停领、API 不导入 ML、正常与两种 ASGI 断线下载句柄关闭。
2. 新前端 5 项回归与既有共 15 项 PASS；构建 PASS。覆盖取消 A 后切换 B、成功 POST 后 detail 失败重放键、
   终态指标错误退避、卸载中止请求、真实终态指标。独立审查复现的三个竞态均已修复。
3. 实际 ML 策略注入 3 项 PASS：固定类名单拒绝未知对象、batch 参数漂移拒绝、非有限 EMA 拒绝，无成功产物。
4. 实际 Uvicorn HTTP + 独立 Worker 单轮 CPU 烟测 PASS：生成的 64×64 矩形图，4 train+4 val，单类，
   nested 路径；1 epoch、batch=1、imgsz=320、seed=0、lr0=.01。真实训练 Job
   `860650a5-6380-461b-abf5-4d16790d70b1` 于 09:25:17–09:25:24 UTC 完成。
   HTTP Job/Artifact/metric 记录位于 `T050/http-*.json`；两份最终 PT 均下载并核对 SHA/size。
   10 项真实指标全部 epoch=1，final-eval 重复回调未进入曲线。源输入在运行结束及发布前重新哈希通过。
   指标值只是合成管线验证，不代表泛化精度或模型效果。
5. 浏览器仅发现/typecheck 5 个场景，实际 Chromium 未在本地执行。新增独立 Linux CPU CI job 获取固定资产、
   hash-lock 安装、真实 HTTP/策略测试、真实训练浏览器；不上传图片、权重、数据库、日志或凭据。

## 原始执行位置与初始失败

本机原始临时证据由执行者保留，仓库只提交安全摘要与受控复现脚本，不发布本机路径。
命令：`cd backend && .venv/bin/python -m pytest tests/test_training.py -q`（35 passed，退出 0）；
`cd web && npm test -- --run`（15 passed，退出 0）；`npm run build`（退出 0）；
`EDGEVISION_ML_POLICY_ROOT=<private-smoke-root> .venv-ml/bin/python -m pytest tests/test_training_ml_policy.py -q`（3 passed，退出 0）。
真实 HTTP 使用 `PLATFORM_DATA_ROOT=<fresh-private-root> EDGEVISION_SMOKE_ASSET=<verified-local-asset> PYTHONPATH=. .venv-ml/bin/python tests/training_http_probe.py`。
仅此显式测试脚本生成私有随机账号；生产启动不生成演示账号或测试数据。

初次轻量回归为 101 passed / 4 failed：旧 train-as-unsupported 夹具、空历史 train provenance 和契约漂移。
保留 unsupported 负向测试并换为尚未实现 export_onnx，历史空输入返回 null provenance；重新生成契约。
首次全量聚合为 138 passed / 2 failed / 3 optional-ML skipped：日志合并后原噪声 flood 不再达到 2000 条。
夹具改成真实安全结构化行与噪声交替，保留配额、尾部恢复与持续 drain 的原断言，不放松上限。
初次真实 HTTP 运行的本地客户端被宿主 SOCKS 环境影响；只给回环测试客户端设置 trust_env=False 后重跑通过。

## 限制与回退

Python 审计不是原生代码/OS 网络沙箱；host power-loss、真实磁盘耗尽、Windows ML/CUDA、正式精度及 ONNX 未执行。
磁盘测试是受控故障/预检，不证明物理磁盘配额。COCO8 仍只私有前检，不发布；当前合成图是测试夹具，不进入产品示例。
回退前停提交并取消/等待活动任务 drain，保留 Dataset、PT、审计及 orphan，不在旧 Worker 下自动处理 queued train。
最终 aggregate 和远端精确 commit CI 结果由后续验收追加，不将本节计划记为 PASS。

## 最终代码本地复核（2026-11-04 09:35 UTC）

补充严格 TrainingRuntime/TrainingArtifactMetadata、实际 base_model_sha256、数值类型拒绝 bool、
操作员探针启动歧义持久化与 Worker 反向停领测试后，再次使用全新隔离根运行真实 HTTP/Worker。
Job `fe86f46a-aaa0-42e1-a198-03c0bf952f0f` 从 09:35:24.330503 到 09:35:32.890559 UTC，成功。
最终可下载 best/last 均 5,455,706 bytes：

- best Artifact `583571ec-1d15-421c-b945-46116b2421ce`，SHA256 `80b87ee4c792efcbc086a109408c752d459d54c3bedad7ca171de5e4edab4e70`。
- last Artifact `e5f7673e-c633-4329-863a-204487c46dc2`，SHA256 `3a8643f69acc1e7a2733f0e79f4128e8446d96632e496d81b78badebcb0e9663`。

记录 `T050/http-final-*.json`。源码逐文件指纹 `T050/final-source-checkpoint.json`。
固定生产默认 nbs=64、warmup_epochs=3.0、lrf=.01，有效 SGD 更新 **1 次**，9 次强制安全加载；
与先前 standalone 特殊 nbs=1 得到四次更新的实验明确区分。模型输出净化后重新加载验证。
日志只保留开始、一次脱敏提示和完成，不再把每行框架输出都显示为警告。

最终真实指标仍为 10 项 epoch=1；mAP50=.36182、mAP50–95=.18991、precision=.28272、recall=1，
train box/cls/dfl=1.29962/3.16239/1.12563，val box/cls/dfl=1.12882/5.81171/1.22799。
这些只说明受控合成数据上的真实运算，不作为准确率声明。

## 最终聚合结果

`bash scripts/dev.sh check` 退出 **0**：纯契约 6 项、脚本/Worker 11 项、pytest **143 passed / 3 skipped**、
前端 **15 passed**、Vue/TS/Vite build 与生成契约漂移检查全部通过。3 个 skipped 是默认轻量环境不安装 ML 的
显式可选策略测试；它们在真实联合 ML 环境另行执行，**3 passed / 退出 0**，不是跳过当通过。
新 T050 轻量测试共 38 项，覆盖上述边界和新增探针启动失败/反向停领与 bool 参数拒绝。
本地真实 Chromium 仍未执行；发现 5 个场景与 e2e TS 检查通过。安全汇总及原始日志摘要见 `T050/final-checks.json`。

最终范围审查仍为 review_required，需对实际发布 commit 的 CI 结果独立判定。没有 commit、push、merge 或 main 改写由本实现阶段执行。

## 独立最终复核

2026-11-04 UTC，代码冻结后独立执行 `python scripts/dev.py check`，退出 0：143 个后端测试通过、3 个可选 ML 测试跳过，15 个前端测试通过，构建和 OpenAPI/TS 漂移检查通过。可选 ML 测试的单独实际执行结果仍见上文，不把轻量环境中的跳过写成通过。最终源码安全检查与 `git diff --check` 通过；远端 CI 尚待本次功能分支发布后运行。
