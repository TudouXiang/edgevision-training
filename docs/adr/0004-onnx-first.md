# ADR 0004：ONNX 作为首版部署主线

状态：已接受，2026-09-23。

决策：支持已训练 PT → ONNX 导出 → ONNX Runtime CPU 加载及样本一致性检查 → 实际图片推理 → 可复现部署 ZIP。模型元数据保留 `target.format='rknn'`、chip 与量化字段及适配器接口；没有 Toolkit 和目标设备实测不提供 RKNN 成功态。

理由：ONNX 可在普通 CPU 环境完成真正的闭环，适合首版验收；芯片工具链与设备不是当前环境的可靠前置条件。影响：产品文案必须标明 RKNN 未实现；增加 RKNN 前需冻结芯片/Toolkit 版本、量化样本、兼容性阈值和 NPU 实测证据，不能把 ONNX CPU 速度当 RKNN 速度。
