# T060 P：固定 Linux CPU 独立源码包工程验收

## 精确证据

2026-11-14 UTC，审查并执行的公开 SHA 为 `685f2efa56165fb5bd45641c81a1539ad94759ea`，
对应本地 `3239da3aef4f63ae7af839305138cd3c90df13fc`，完全相同的 tree 为
`f3822aa07269b52407df203368b3ff7039802588`。
[工作流 #44 / 43632501786](https://github.com/TudouXiang/edgevision-training/actions/runs/43632501786)
的 Linux job `132562079352` 在 19:38:19 UTC 输出 schema 5、stage=complete、status=passed，十二阶段全部 passed：

`isolation → dependency_check → training_http → export_http → onnx_policy → training_policy → browser_delivery → inference_http → inference_policy → inference_browser → package_http → package_browser`。

Windows process job `132562079045` 与普通 checks job `132562079408` 均已读回 completed/success；#44 三个任务全部成功。
本地最终普通后端回归：858 passed、14 原生 opt-in skipped、42 subtests passed（392.57 秒）；
前端 130 passed，build、E2E typecheck 通过。P 专用发现恰一例且未执行；实际执行以 #44 为准，不把发现或 skip 当成验收。

## 要求与证明对应

|要求|实际证明|边界|
|---|---|---|
|可信来源与同项目 Worker 闭环|当前源模型、导出/训练父链、冻结输入与严格 DTO；真实 package HTTP/Worker 创建、幂等重放及鉴权下载|不接收任意路径、URL、模型或生成代码|
|固定独立 ZIP|11 个固定成员；清单、每项大小/hash、模板/模型/代码/依赖摘要；固定 ZIP 结构校验|不发布原始训练数据、会话、数据库或私有模型|
|不依赖平台后台的执行|新建九依赖 venv；Python `-I`，清理 PYTHONPATH，限制解释器/配置/RECORD/导入来源；raw 与 CLI 分别在新受管子进程中运行|无 app/FastAPI/Torch/Ultralytics；依赖不是借用后台 venv|
|真实模型/数值比较|同源平台 ONNX reference、独立 raw、独立 CLI 三阶段，比较完整 raw 张量、检测及预处理/预览；已下载 HTTP ZIP 再执行 CLI|固定 YOLO11n、CPU、合成输入工程烟测；保留原容差，不是精度或性能报告|
|实际 UI 交付|真实会话与通过的 HTTP 证明；创建包、同步双击只有一个新任务、ZIP 下载大小/hash、刷新恢复已接收身份、离线恢复、375px 宽度断言|浏览器下载按已验证产物摘要核验；不是人工审美或完整无障碍评测|
|安全退出与不假成功|完整受管 receipt、源码/运行环境再绑定、intent/rename/CAS；能力证明失效即不可用；服务及任务树收敛|未穷举原生断电、每个取消窗口、并发负载或所有故障组合|

执行隔离保持非 root、无外网、无宿主目录挂载、无新增 capabilities、no-new-privileges、资源上限；
共享 450 秒及外层 480 秒预算未放宽。公开回执只含固定阶段与结果，原始诊断、权重、下载包和会话留在一次性私有环境。

## 使用与范围

限定目标为 Linux x86_64、glibc >= 2.28、CPython 3.12、CPU、平台可信 YOLO11n ONNX，协议 `edgevision-python-onnx-v1`。
ZIP 包含 ONNX、固定 `run.py`/推理核心、示例、清单、依赖锁和许可/来源说明，**不含 Python 解释器或 wheels**。
首次安装需要网络，或者用户另备适配目标的 wheelhouse；不能称开箱即用的离线包。
包内 README 给出 hash-locked 安装和 `python -I run.py --image example.png --format png --output results` 命令；输出目录必须全新。

每个产物仅声明 `trusted_model_fixed_package_integrity` 与 `standalone_execution=not_run_for_this_artifact`。
真实模板独立运行证明不代表每个后续包都执行过模型，更不代表准确率、用户数据权利或特定硬件已通过。
每个实际部署环境仍须当前源码绑定的 operator probe，不能复制 CI 能力文件。

## 保留失败历史

- #36 `43623696620`：P HTTP 失败，十个既有阶段通过。
- #38 `43625172940`：定位至 `probe_identity`。真实 venv 副本回归证实旧路径相等检查不正确；改为固定基础解释器字节身份，保留配置/启动钩子/九依赖全 RECORD 检查。
- #40 `43627012194` 两次：E browser_delivery 失败，I/P NOT_RUN；不当作 P 修复效果证据。
- 新回归证实无有效 P 证明时提前哈希运行环境是无用开销；先拒绝缺失/无效证明，有效证明仍全量验证。没有降低业务断言。
- #42 `43630286972`：schema 4 十一阶段全过，只支持 P HTTP，不能替代 #44 的 P UI 证明。

结论范围：P 在上述固定目标/可信模型的工程路径已取得真实独立运行及浏览器闭环证据。
Windows ML、CUDA、NPU/RKNN、离线依赖交付、正式准确率/性能、完整生产故障矩阵、T070 和整个项目最终验收不在本记录范围。
