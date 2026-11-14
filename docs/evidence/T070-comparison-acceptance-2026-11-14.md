# T070 基础实验对比工程验收

限定结论：基础实验对比通过固定 Linux x86_64 / CPython 3.12 / CPU / 可信 YOLO11n 的真实浏览器验证；不代表 T070 整体、正式精度实验或用户机部署完成。

- 精确远端提交：`0a204d9382386ff801e9dce410c8ef554fa7a7d4`
- tree：`63a74384d5d4bcb8fd3c89c4cbfcdc08f510753c`
- 本地对应提交：`22b92521044a1d6d13fc73006589d049f593cf6d`
- [原生及普通 CI #53](https://github.com/TudouXiang/edgevision-training/actions/runs/43640192379)：checks、windows-process、linux-training 全部 success。
- checks：866 后端 passed、14 原生 opt-in skipped、157 前端 passed；契约一致、构建成功。普通浏览器 discovered=6 / executed=5 / passed=5 / skipped=1（ML 预期跳过）/ unexpected=0。
- linux-training job `132585913371` 在 `2026-11-14T21:02:53.1332130Z` 返回 schema_version=5、stage=complete、status=passed；十二阶段 isolation/dependency_check/training_http/export_http/onnx_policy/training_policy/browser_delivery/inference_http/inference_policy/inference_browser/package_http/package_browser 全部 passed。

`web/e2e/t050.e2e.ts` 在隔离受控合成数据上实际创建两个不同 CPU 1 epoch 任务，逐个检查真实成功状态，以 API 最终指标逐项核对界面对比值；没有复制数据库任务、伪造指标或把训练指标叫测试集精度。界面展示不可变来源与参数，不同来源警告，缺失值不按零处理；读取上限和游标完整性失败时不展示伪完整结果。原 E/I/P 闭环在同一精确版本重新通过。

## 失败与修正保留

#49（213726f）原生停在 ui_training_result，最初阶段过宽，不能据此判断训练失败。#51（173d08c）新增固定匿名子阶段后明确停在 ui_comparison_inventory；第二次真实训练名称及 succeeded 断言此前已通过。独立源码核查发现隐式 label 包含 SELECT/OPTION 全部文本，Playwright exact getByLabel 无法匹配。为两控件添加明确 aria-label，保持原 exact 定位、业务断言和预算。新单测先失败再通过，#53 原生确认修正。失败版本 I/P 为 NOT_RUN，不篡改为通过。

本地补跑后端曾因 cwd 不当发生 app 导入失败；正确 cwd 重跑被中断，不计通过。本报告后端全量数字来自已成功的 #53 CI。基础实验对比不引入 API/数据库迁移；用户数据、模型、凭据、原始私有日志不发布。

## 仍未完成

正式固定真实测试集精度/性能实验、A01–A16 全矩阵整体验收、用户机干净部署、演示及论文材料、main 集成另列任务。无真实数据许可与划分记录时不编造准确率；合成工程烟测不外推泛化效果、Windows ML 或 GPU/NPU。
