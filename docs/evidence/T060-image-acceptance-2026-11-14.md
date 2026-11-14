# T060 I：固定 Linux CPU 工程验收证据

## 精确版本及结果

2026-11-14 UTC，公开提交 `bd8d554b6bc51d05d6c1b81119ea8e1416eed5b9`，
树 `c21a8d54ee8222d7f9402ca08aa0bdb01cd2e47e`，
[工作流 43612577523](https://github.com/TudouXiang/edgevision-training/actions/runs/43612577523)
的 checks、windows-process、linux-training 三个 job 全部 success。

- checks 132500670661：684 后端通过、14 原生 opt-in 跳过；117 前端通过，构建与契约通过；
  普通 HTTP 重启、独立 Worker 与整树退出探针 passed；普通浏览器步骤 success。
- windows-process 132500670735：既有 Windows 进程矩阵 success，不是 Windows ML。
- linux-training 132500670467：显式绑定上述 SHA，非 root、无外网及无宿主挂载的既定隔离环境；
  未改变共享 450 秒、外层 480 秒及 20 分钟 job 上限。
  匿名 schema_version=3、stage=complete、status=passed，十个有序阶段全部 passed：
  isolation、dependency_check、training_http、export_http、onnx_policy、training_policy、
  browser_delivery、inference_http、inference_policy、inference_browser。

## 需求映射与限界

|要求|证据|限界|
|---|---|---|
|可信同项目 PT/ONNX、不可变图像和来源绑定|inference_http 实际生产接口；既有严格 DTO、权限和篡改负测|不支持任意 PT/路径/URL|
|真实 PT 与 ORT CPU 图片执行|inference_http、双模式生产 probe、inference_policy|固定 YOLO11n、640 FP32、合成图片工程烟测，不是精度评测|
|预处理、NMS、坐标及双模式一致性|共同 delivery_infer 核心；算法合成回归；原生固定 raw/detection 容差|不放宽既有 raw atol/rtol 1e-4、检测匹配规则|
|真实浏览器提交及结果|PT/ONNX 顺序上传/提交、实际结果、preview及下载摘要、刷新、断线恢复、窄屏断言|不是人工视觉审美或完整可访问性验收|
|重复点击只有一个任务|按钮 enabled 前置断言、同步双击、完整 jobs 差集必须恰一项|历史失败仅定位 submit，不能据一次通过断言所有竞态消失|
|不假成功及恢复安全|既有受管进程、发布/篡改/退出失败单测与审查；实际完整链路通过|未穷举原生断电/每个取消窗口|

此前三次失败保留：43607336609 为 inference_browser，43609069043 为 browser，
43610853801 为 ui_pt_submit。只增加固定匿名诊断与 enabled 断言，未降低业务断言或模型验证。
正常运行没有发布图像、权重、会话、原始日志、数据库或私有模型记录。

此证据只支持 I 在上述固定 Linux CPU 范围的限定工程验收。P 独立部署包、T060 整体、
T070、Windows ML、CUDA、NPU/RKNN、正式精度和性能、完整生产故障矩阵均未由本记录证明。
每个实际部署环境仍须当前绑定的能力 probe，不能复制 CI 的可用状态。
