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

## T060 E 实际候选契约与历史示例的区别

以上通用 `ModelMetadata` 是早期设计示例，不再作为 ONNX 公共分支的宽松回退。
现行候选由 `schemas.OnnxArtifactMetadata` 定义：

- `provenance` 完整绑定当前 job/run、冻结输入摘要、源 Artifact/训练 Job、PT 摘要和大小、源元数据与训练输入摘要、训练来源、代码和联合环境。
- `validation` 绑定同一 job/run/input/source，并保存原始图及模型摘要/尺寸、类别顺序、固定 IO、checker 成功、精确版本和 CPU provider。
- 三个公开可重建 RGB FP32 张量（zeros/gradient/pattern，`rgb-fixed-v1`）逐个保存输入、PT raw、ORT raw 的 SHA-256、比较元素数、最大绝对误差及最大容差比。
- 输出固定 `[1,4+nc,8400]`，输入固定 `[1,3,640,640]`，opset18、IR8、FP32，无动态尺寸/简化/图内 NMS。
- 所有 raw 元素必须有限，且 `abs(ORT-PT) <= 1e-4 + 1e-4*abs(PT)`。阈值已冻结，不能为了通过修改。
- 原始图不重写；递归拒绝 external TensorProto、稀疏张量、custom/unknown operator、局部函数、训练图和不支持的 IO。
- 验证范围明确为 `checker_ort_raw_tensor_equivalence`，不是单图产品推理、精度实验或独立部署验收。

`validation_sha256` 绑定单独的验证文件；DB Artifact 的 hash/size/job 还需与 metadata 对齐。
缺字段、额外字段和矛盾绑定不能通过公共 DTO 的通用 object 分支。这一结构和完整发布逻辑已重建；实际 ONNX/ORT 执行仍 **NOT_RUN**，待另行获准的无外网边界与新证据。
