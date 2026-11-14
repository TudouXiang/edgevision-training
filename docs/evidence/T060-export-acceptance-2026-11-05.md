# T060 E：限定工程验收（2026-11-05 UTC）

## 范围和精确版本

E（同项目可信 PT 的固定 ONNX 导出）在固定 Linux CPU / YOLO11n 范围 **限定 accepted**，可进入 I 单图推理实施。T060 整体尚未 accepted，I/P 仍未实现；不能据此称 A13/A14/A15 全表通过。

验收是两份分开的增量证据，不是声称每个提交都重跑过原生 ML：

1. `76af48f5eb86568f778efe5555f8e76074f3b978` 的 [run 41976886829](https://github.com/TudouXiang/edgevision-training/actions/runs/41976886829) 实际完成七阶段隔离 ML、HTTP 和浏览器验证；[原件摘要与证据说明](T060-isolated-ml-2026-11-05.md)。
2. `7e322689831216f53fd3c26eea009c580c8c35f3`，tree `c173cc59a1532671489f269153ca82b2940c8551`，补齐既有契约要求的错误分类。独立复核 accept，新加 33 项轻量/普通受管进程测试通过；新提交没有重跑原生 ML。

独立审查移除新增异常边界包裹及相应异常类导入后，比较整个 `export_and_validate` 函数 AST，与 `76af48f` 的正常执行表达式和顺序完全一致。导出参数、checker/ORT 所读图、张量、容差和发布规则没有放宽。这支持有限增量验收，不等于新 SHA 的原生运行回执。

## 逐项映射

| E 需求 | 证据与结果 | 限界 |
| --- | --- | --- |
| 同项目可信来源、授权、固定参数、幂等 | `export_inputs/service`、严格 DTO 与轻量 API 负测；真实 HTTP/浏览器绑定训练产物 | 不支持外部 PT、任意路径/URL、额外导出开关 |
| 原始图同字节 checker→ORT CPU | 精确原生 `export_http` 阶段、原生 graph policy；原图摘要及发布绑定 | 固定 Linux CPU/YOLO11n/640/FP32/opset18/IR8 |
| 数值一致性 | 三种冻结 RGB 张量，全 raw 有限元素，atol=rtol=1e-4；真实执行通过 | 不是单张照片检测精度或正式实验 |
| A12 完整束与不错误成功 | 缺/坏/额外/链接产物、错来源/验证、无 drain、取消竞争、CAS/rename 窗口注入；普通实际子进程 exit0 无产物、Worker 丢失 | E 发布窗口主要是函数级注入与共用恢复回归，不冒称每个原生中断/掉电窗口实测 |
| 缺 ORT、坏图、不 fallback | 原生 parser/ORT 构造失败注入；真实轻量缺 ORT；新封闭错误码与普通受管失败链 | 未做“仅卸载 ORT 的完整 ML HTTP 环境”实验；原生 corrupt 不是完整负向 HTTP E2E |
| 鉴权下载 | 同一描述符 hash/size、完整来源和验证绑定；跨用户拒绝/篡改拒绝/增长限额；真实 HTTP 与 Chromium 下载 | 不公开服务器路径或运行原始记录 |
| UI 中断与重复操作 | 真实浏览器训练→导出→下载、重复点击、断线重连、路由重入与幂等重放；组件晚到请求/刷新回归 | 不将未执行的人工视觉、原生运行中取消窗口泛称通过 |

## 本轮修补的契约问题

前轮独立审查发现 `docs/contracts.md` 要求的加载失败、算子不支持、缺依赖被汇为 `RUNNER_FAILED`。原行为会失败、不发布，没有发现 PT fallback 或假成功；但不满足明确报错契约，因此先修补再放行。

固定子进程退出码只用于 export_onnx 的公开 Job 映射：

- 73 → `ONNX_DEPENDENCY_UNAVAILABLE`：缺发行包或导入失败。
- 74 → `ONNX_MODEL_INVALID`：图读取/解析/结构/checker/数值验证失败。
- 75 → `ONNX_OPERATOR_UNSUPPORTED`：受控图中的 custom/unknown 算子或精确 SDK unsupported 类型。
- 76 → `ONNX_RUNTIME_FAILED`：ORT 初始化、加载、执行等运行异常。

类型识别不解析上游异常文本；公共日志只有封闭代码。原存储错误仍走 70，安全策略仍走 68，KeyboardInterrupt/SystemExit 不被包装。未知退出码、非导出 Job 不借用这一协议。导出探针失败也不会产生 available 记录。

## 实际新增验证

在项目轻量解释器中、清空原生 opt-in 环境变量后执行：

`cd backend && EDGEVISION_ONNX_POLICY_ROOT= EDGEVISION_ML_POLICY_ROOT= .venv/bin/python -m pytest tests/test_export_errors.py -q`

实现侧 33 passed / 9 warnings / 16.67 秒 / 退出0；独立复核同33项通过 / 17.41 秒 / 退出0。测试覆盖四类具体错误、匿名输出、安全/存储/控制异常保留、固定 SDK 类型匹配、无效代码拒绝、runner 不建束、实际 Worker→guardian→task_process→drain→HTTP failed、零 Artifact、同键不重复和不导入 ML。

标准库专用 `-I -S` 子解释器还直接执行生产 `load_ort()`，确认 ORT 发行包实际不存在时抛 `PackageNotFoundError`，没有任何模型框架导入。这不是卸载操作，也不是其它 ML 包完整存在的环境。

结构回归明确检查所有读图、parser/checker、SessionOptions、provider/IO、session.run、数值比较均处于对应封闭异常边界；该静态测试不冒充模型执行。

冻结源码 `7e322689` 的最终整合 `EDGEVISION_ONNX_POLICY_ROOT= EDGEVISION_ML_POLICY_ROOT= EDGEVISION_SMOKE_ASSET= python3 scripts/dev.py check` 退出0：462后端通过/9原生opt-in跳过、47前端通过，构建与契约无漂移。单独实际HTTP/API重启探针退出0，`http_api_restart=passed independent_worker=passed tree_exit=passed`。随后仅更新阶段文档与其回归断言，5项文档测试通过；没有改变运行源码。公开分支的最终精确CI状态仍需对应发布SHA留档。

失败历史保留：第一条聚焦pytest命令误从仓库根运行，因`app`不在导入路径收集失败，改为既定backend目录后通过；新增结构回归曾发现末次读图仍在异常边界外，修补后33项通过。修补中途的456后端/9跳过结果仅为初版，不冒作最终冻结源码的462项结果。

## 能力启用与未执行项

本补丁改变代码绑定，旧训练/导出 probe 记录不可复用，不能复制旧 runtime_binding 伪造 available。实际启用新代码环境仍必须通过绑定当前源码/解释器/发行记录/锁的受管 probe；运行前继续遵守对应授权和安全审查。工程阶段放行 I 不会取消此运行时硬闸门。

I 产品单图 PT/ORT、P 真正独立部署包、Windows ML、CUDA、NPU/RKNN、正式精度/性能、全部生产故障矩阵和 T070 都未由本次验收证明。没有发布真实图片、权重或私有运行目录。
