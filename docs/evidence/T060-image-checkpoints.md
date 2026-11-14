# T060 I 源码检查点（2026-11-05 UTC）

此记录是增量开发证据，不是 I 原生验收。E 既有受限验收见原记录；P 始终501。
ADR0014 的设计在 d2f9f5197b936a4b7812d916053d728f81e0bde9 经独立只读审查 accept，随后获准源码、
轻量与普通受管进程实施。真实 ML/ORT/probe、下载和推送没有放行，也没有执行。

## 1. 严格契约和共同算法

新增 I 公共/内部严格 DTO、kind 判别 Artifact 分支、可空 JobPublic.inference、重试来源字段，
以及新增净化 preview 路由契约。图片、infer 与 preview 入口此时仍501，能力未开放。
`delivery_infer.py` 是无平台/模型依赖的共同算法源，覆盖 Pillow 有界解码、EXIF/tRNS/alpha、整数
letterbox、LE FP32张量、稳定单标签类别内NMS、clip、preview、固定合成PNG与双射匹配。
它不是已运行真实模型的证据；ORT适配尚待后续阶段接通。

实际命令：
- 首次从仓库根误运行 `backend/.venv/bin/python -m pytest backend/tests/test_image_algorithm.py -q`，
  退出1（23项 ModuleNotFoundError: app），未运行算法。修正工作目录后重跑。
- `cd backend && .venv/bin/python -m pytest tests/test_image_algorithm.py tests/test_inference_contract.py tests/test_contracts_unit.py -q --basetemp=.test-tmp-stage1`：退出0，60 passed、8 subtests passed。
- `backend/.venv/bin/python scripts/export_contract.py`：退出0，生成OpenAPI/TS，未手改生成文件。
- `backend/.venv/bin/python scripts/export_contract.py --check`：退出0，无漂移。

测试是纯数学/Pillow合成输入：严格类型、cross-binding、空结果、同类NMS/tie/边界、候选/结果上限、
极端有限几何、EXIF八方向尺寸、透明模式、坏图/动画/模式/像素限制、张量layout/hash。不是PT/ORT推理。
开发用 backend/.venv 与 web/node_modules 链接仅复用既有轻量依赖，不入Git、未安装新包。
全量回归/普通进程/真实模型/浏览器：此检查点 NOT_RUN。

## 2. 后端完整源码候选（尚待完整审查）

上传/来源/提交、固定runner、完整束发布/鉴权历史读取、Worker分派和双模式operator probe已接通源码。
所有新执行仍要求当前真实双模式probe，默认轻量环境 fail closed；P保持501。
独立检查修正了PNG16编码被Pillow降位的漏洞，以及复用旧FileEntry造成I证据整数/尺寸宽松的问题。
I来源DTO补完整PT provenance/epoch/digests及ONNX嵌入E来源绑定，保留旧T050/E schema。
公开I字段形状未变，图片/结果路由文档现在声明实际错误状态；OpenAPI/TS重新生成。

实际增量执行：
- `cd backend && .venv/bin/python -m pytest tests/test_image_algorithm.py tests/test_inference_contract.py -q --basetemp=.test-tmp-stage1-fix`：退出0，64 passed。
- `tests/test_dataset_api.py tests/test_export.py` 初次回归退出1：85 passed，1项旧infer仍501断言不再适用；改为不存在图片404，P仍要求501。该次不是全通过。
- `tests/test_inference.py -xq --basetemp=.test-tmp-inference`：退出0，27 passed。合成PT/ONNX/完整束夹具，不执行原生模型。
- 新upload测试首次误引用不存在的fixture，收集退出2；修复fixture导入后重跑。
- `tests/test_inference_upload.py tests/test_inference_probe.py -xq --basetemp=.test-tmp-upload-probe`：退出0，25 passed。
- API/Worker/probe/runtime导入检查退出0，没有加载Torch/NumPy/ONNX/ORT/Ultralytics。
- 契约重新生成与漂移检查：退出0。

raw比较负例覆盖截断、增长、hash变化、NaN/Inf、超容差、对齐及不同hash但容差内的全部元素比较。
普通受管进程与全量回归仍在下一阶段运行；真实I probe、PT/ORT模型、HTTP/浏览器原生链仍NOT_RUN。
本检查点没有安装、下载、运行真实ML或推送。新增HTTP/隔离原生验证入口由独立工作区负责。

## 3. 独立审查修正和受管进程证据

- af2候选的新增I五组测试合计128 passed，退出0（含普通Worker/guardian树取消、GO前取消、
  Worker丢失、exit0缺束及8类闭合错误码）。这些受管子进程使用显式测试夹具，不加载模型。
- 独立审查复现下载在完整束核验之后、打开同一描述符之前文件消失/换symlink时漏出500；
  将路径解析与context创建纳入409边界。4项HTTP竞态与2项嵌入旧schema类型拒绝：6 passed，退出0。
- 来源检查/复制/后置copy校验用窄完整性边界；OSError保留70 STORAGE_UNAVAILABLE，ValueError来源变动66、
  runtime版本/绑定67，缺ORT保留独立86。infer/probe_child使用同一异常边界，不以任意异常文本猜分类。
  完整task_process.execute→exit的10项前/后置注入测试全部通过，未进入原生模型适配器。
- 原始比较/共享probe恢复/缺ORT归类/无ML导入12 passed，退出0。
- 上传rename后再次核对持有描述符的原文件身份；I嵌入旧T050/E schema拒绝标量coercion，不改变历史schema。

以上针对增量源码，新增契约说明位于contracts/api/storage文档。全量回归另行绑定最终候选；
正在进行的早先全量运行不能冒充最新修正的精确SHA结果。PT/ORT真实模型、I operator probe及原生HTTP仍NOT_RUN。

## 4. d774精确全量与I限定metadata错误边界

在 `d774cb2fb2eec307652e3b23b734edca7283a40b` 源码保持不变期间运行：
`cd backend && .venv/bin/python -m pytest -q --basetemp=.test-tmp-final-d774`，退出0，
**608 passed、9 skipped、42 subtests passed**（364.21秒）。9跳过是既有原生门控测试，不是原生成功。
更早一轮运行中有后续编辑，591 passed/9 skipped仅作过程记录，不冒充此精确SHA。

独立审查另确认I输入/结果的Artifact detail/list遇坏metadata时，原样沿用旧通用序列化会漏500。
最后仅对 `inference_input/inference_result` 在响应前执行严格DTO验证并映射规范409 ARTIFACT_UNAVAILABLE；
PT/E历史序列化路径保持原状，不静默省略坏项。4项HTTP合成回归全部通过，契约检查退出0。
此为上述全量之后的单独增量；最终整合全量由合并工作区另记，不把d774全量自动转移到新SHA。

开发链接、临时测试目录和日志均不入Git。真实ML/ORT、当前I capability probe、原生HTTP/浏览器、Windows ML
继续NOT_RUN；没有模型/用户图片/原始日志/凭据进入源码或公开交付物。
