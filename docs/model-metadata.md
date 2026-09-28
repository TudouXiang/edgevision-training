# 模型元数据与验证

`artifacts.metadata_json` 的模型记录最低形态：

表列 `metadata_schema_version` 和 JSON 内 `schema_version` 同步为 1；文件校验状态在 `0002_foundation` 为 `unverified/passed/failed`，只有 passed 且有真实证据才允许供后续部署选择。

```json
{
  "schema_version": 1,
  "family": "YOLO",
  "task": "detection",
  "source": "trained_best",
  "dataset_id": "<uuid>",
  "source_job_id": "<uuid>",
  "parent_artifact_id": null,
  "framework": "Ultralytics",
  "framework_version": "<actual-version>",
  "architecture": "yolo11n",
  "input": {"shape": [1, 3, 640, 640], "color": "RGB", "layout": "NCHW", "normalization": "0..1", "letterbox": true},
  "classes": ["class_0"],
  "output": {"schema": "<observed-output-schema>", "nms_in_graph": false},
  "training": {"epochs": 1, "seed": 0},
  "validation": {"runtime": null, "result": "unverified", "evidence_key": null},
  "target": {"format": "pt", "chip": null, "quantization": null}
}
```

示例中的类名/轮次只是**字段示例**，不是实验结果。记录中的每一项须来自真实训练配置、文件或运行时；未知填 null，不能编造值。artifacts 表另存 SHA-256、字节数、验证状态与时间，不能仅靠 JSON 自报通过。

ONNX validation 至少含：导出命令/实际版本/opset、文件哈希、ONNX Runtime CPU 载入成功、实际 input/output schema、固定真实图片与预处理、原 PT 与 ONNX 检测结果比较方法/阈值/实测、至少一次真实 ONNX 推理输出与证据路径。阈值在实验前冻结；没有 PT 对照时只能标注加载/运行通过，不能宣称数值一致性通过。部署 ZIP 带元数据清单、哈希、ONNX Runtime Python 单图示例和说明；RKNN 的 target 仅扩展字段，无执行和通过标志。
