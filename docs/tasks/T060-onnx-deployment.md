# T060：ONNX导出、推理与部署包

执行者：实现Agent。前置：T050 已在固定 Linux CPU 范围 accepted；E 在固定 Linux CPU/YOLO11n 工程范围限定 accepted，见[逐项验收](../evidence/T060-export-acceptance-2026-11-05.md)。I 已完成 ADR0014 设计冻结和源码独立审查，业务仍处于 review_required，见[I整合记录](../evidence/T060-image-integration-2026-11-05.md)；真实模型/浏览器未执行。P 保持 blocked 直到 I 验收；T060 整体尚未 accepted。当前仅 P 仍501。新绑定的实际能力 probe 尚需按运行环境执行，不复用旧记录。

目标：export_onnx、infer、package接入同一Worker；只处理平台可信模型。固定导出参数，生成完整模型元数据；按实际格式执行PT/ORT；固定模板产生独立Python部署包。

不做：任意模型互转、动态尺寸/量化开关、RKNN、LLM在线生成代码、视频或远程设备。

验收：A12-A14。导出先checker再ORT实际执行；输入宽高/颜色/补边/归一化/NMS与坐标正确；故意损坏ONNX或卸载ORT后明确失败，不回退PT。空检测和边缘框通过测试。

部署包在独立环境运行，不依赖项目后台安装包或API，记录模型/代码/依赖摘要与命令。相同样例PT/ONNX差异按预先定义的匹配和容差衡量，不把每个浮点完全相等作为默认标准。

输出docs/evidence/T060-report.md、模型manifest及部署包执行证据；需要下载独立环境依赖时先核对授权。
