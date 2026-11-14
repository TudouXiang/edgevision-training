# ADR 0015: T060 P 独立 ONNX CPU 部署包

日期：2026-11-14。状态：已实施并通过固定范围工程验收；精确版本、独立运行及浏览器证据见 [P 验收](../evidence/T060-package-acceptance-2026-11-14.md)。以下保留设计约束，不将设计文字单独作为运行证据。每个实际环境的部署能力仍须当前源码绑定的 probe。I 的限定验收见 `../evidence/T060-image-acceptance-2026-11-14.md`，不扩张为 Windows ML、GPU/NPU、精度或全项目验收。

## 1. 目标、选择与边界

让用户把本平台可信 ONNX 导出为固定模板 ZIP，在没有 EdgeVision 安装、数据库或 API 的新环境中执行单张图片。使用现有 Python、Pillow、NumPy、ONNX、ONNX Runtime CPU；不引入新运行依赖。选择是受托工程决定，不声称用户逐项选择过。

比较：复制整个后台虽省开发但破坏独立性；容器/打包解释器引入镜像及二进制许可、平台负担；采用可审计 Python 源码 ZIP 与精确 hash lock，最小且可验证。ZIP 不含解释器、wheel、site-packages、Torch、Ultralytics、训练数据或用户图片。首次依赖准备需要网络或离线 wheelhouse，不承诺双击运行或下载后即离线可用。

仅固定 Linux x86_64 CPU / Python 3.12 / detection-image-v1 / 静态 batch1、640×640、FP32、opset18。默认 confidence=.25、iou=.45，允许 CLI 在 [0,1] 内有限数调整，绝不改算法。Windows 原生、GPU、NPU、量化、任意模型、视频、服务端 HTTP 推理、远程部署均不做。

## 2. 现有接口与来源

复用 `POST /api/v1/projects/{id}/jobs` 的 package kind、Idempotency-Key；保留现有 PackageParams 的唯一参数 `onnx_artifact_id` UUID，不新增用户可选 target。内部目标固定 `onnx_cpu`。PackageJobCreate 增量加入可空 source_job_id，沿用 I 显式重试协议。不接受路径、URL、脚本或额外文件。

仅同项目、passed、succeeded export_onnx 的 ONNX，完整 E metadata/validation 束及父 PT 可信训练来源反复验证。提交冻结来源、class 顺序、model hash/size、协议、模板/核心/lock/notice 摘要和生成器版本；提交、复制、构建后、发布前重验。不得把 E 的 raw 检查当 P 的独立执行证明。当前 I capability 必须真实且绑定新鲜；如果 P 修改共享 identity 导致 I probe 失效，必须重新运行，不复制旧记录。

JobPublic 增加可空 package 来源摘要；deployment_zip 从 OtherArtifactPublic 移入严格判别 DTO，metadata 含 schema_version=1、job/project/model lineage、ZIP size/hash、manifest size/hash、模板/核心/依赖绑定、validation_scope。其他 dataset_report 不收紧。发现历史成功 deployment_zip 数据则先停止并制定兼容方案；现有占位无成功数据不能作为未经检查的假设。

## 3. 包结构与完整性

固定成员：`manifest.json`, `model.onnx`, `run.py`, `delivery_infer.py`, `requirements.lock`, `README.md`, `example.png`, `LICENSE`, `LICENSE_SCOPE.md`, `THIRD_PARTY_NOTICES.md`, `MODEL_NOTICE.md`。不包含私有数据库/session/日志/原始探针数组/用户图片/训练数据；example.png 使用现有 deterministic synthetic_png。所有文件来自固定模板或已核验模型；不从用户目录遍历取文件。

manifest 为严格 schema v1、UTF-8、无 NaN、无重复键、最大 1 MiB。固定 target/protocol、来源摘要、类名有界列表、各非 manifest 成员 path/size_bytes/sha256、核心/模板/lock 版本；manifest 不自哈希，外层 Artifact 与发布 evidence 绑定 manifest 和 ZIP hash。hash 是完整性检查，不宣称数字签名或抵御攻击者同时改源码和清单。

model 最大 128 MiB；example 最大 1 MiB；其他单成员最大 1 MiB；成员固定 11 个；ZIP 和总解压字节均最大 144 MiB。ZIP_STORED，固定 1980 时间戳、普通文件 0644、稳定排序、不加目录条目、不含压缩加密/external attrs symlink。拒绝绝对路径、反斜杠、..、重复名、大小写冲突、额外成员及格式不符。构建器只创建 ZIP，不接收用户 ZIP；下载端仍重验 ZIP 结构及逐成员摘要。

`delivery_infer.py` 原样复制，hash 等于构建来源；平台的纯标准库 `package_cli.py` 原样复制为 run.py，提供共享 validate_manifest/verify_package 纯校验，无需 jsonschema。run.py 只能调用核心 decode_image/preprocess/load_onnx/postprocess/preview_png，不复制算法或 import app；在 Python -I 下显式按已核验文件路径加载自己的 delivery_infer.py，不依赖 cwd/sys.path 或用户同名模块。现有 load_onnx 同时依赖 ONNX checker，不能为了缩依赖删掉 ONNX 校验。严格 CPU provider、禁止 fallback、固定版本/IO/graph、像素/文件限制沿用 I。

run.py 使用标准库先解析并校验清单与所有固定文件，拒绝符号链接/非普通文件；从已核验文件描述符复制模型到本次私有工作目录，再调用核心，避免校验后路径替换。包不可写/只读安装也应能运行；工作目录使用 tempfile，退出删除自有临时文件。不修改模型与包。输入通过显式 `--image` 选择本地 PNG/JPEG，输出 `--output` 必须新建目录，拒绝覆盖或链接目标，输出写入失败时保留部分目录，不自动删除文件（跨进程 stat/unlink 无原子所有权保证）；返回失败，操作者确认后自行处理。输出固定 result.json、preview.png（单独 CLI schema，不伪造平台 job/Artifact UUID），含模型/输入/代码摘要、params、runtime、detections、image/preprocess/preview。固定错误码退出，无 traceback/环境变量/用户完整路径；不要自动 pip、下载、请求后台或运行 shell。

## 4. 依赖与许可

requirements.lock 是现有联合 lock 中 Pillow12.3.0、NumPy2.5.4、ONNX1.23.2、ORT1.31.1 的完整传递闭包，版本/hash 原样保留；复用 cf97d02 保存的九包官方 METADATA 声明闭包证据，并从精确 wheel METADATA 复核闭包，再在无平台依赖的 venv 验证 `pip check`。缺 wheel/hash/适配 Python ABI 即阻断，不改上游锁版本凑通过。README 给 `pip install --require-hashes -r requirements.lock` 与离线 wheelhouse 用法，安装不是 run.py 的副作用。

原项目源码 AGPL-3.0-only，保留完整 LICENSE、原始版权与 LICENSE_SCOPE；源码形式随包提供 runner/core，模板源与对应精确项目源版本可取得。THIRD_PARTY_NOTICES 摘要不是完整 wheel 许可集合；不把依赖 wheel 装进 ZIP。记录精确依赖的许可/NOTICE 来源，不杜撰版权。MODEL_NOTICE 明确模型/数据不被项目 LICENSE 重新授权，保留能证实的来源、hash、原有权利说明；未知项明确 unknown，不把可信模型技术来源当分发权。

当前包只通过鉴权返回所属用户，不执行外部公开发行；固定 base asset 已有 AGPL manifest 记录，保留它的精确来源和条款，但不能据此推断用户训练数据权利。实施与私有工程验证可先用已获准的测试模型；未来向第三方发布模型包前必须核实该精确模型的再分发权及应附条款。若权利证据不足，阻断公开发行，不阻断编写源码、合成测试或授权私有验证。参考 prototype ZIP 始终禁止引入。本 ADR 不作法律认证。

## 5. 单队列、验证与原子发布

沿用单 Worker/单重任务槽、worker.lock、guardian、GO、取消、drain/started/logs_complete/exit0 receipt；不嵌套任意 Popen 或加队列。package runner 只做来源、固定模板与完整 ZIP 字节校验，不导入 ML、不执行模型。每包 metadata 明示 standalone_execution=not_run_for_this_artifact、validation_scope=trusted_model_fixed_package_integrity；不得把 ZIP 成功当成独立模型执行成功。P 首次开放必须另有精确模板及候选包的独立环境实跑证据。此取舍复用旧 cf97d02 proposed D1，避免每次打包重复运行模型与额外进程；不是扩大验收范围。

每个生产 package 子进程仅构建并校验固定包，不执行 standalone 推理。独立证明不要求历史同模型 I 任务；比较进程各自只 load_onnx 一次。独立 CI 或显式 package probe 用已有 guardian 顺序启动全新子进程，生成/读取同源已核验 I 私有参考结果，再与 standalone 结果按冻结检测匹配规则（IoU>=.99、score差<=.001、xyxy各<=.5px）比较。双模式 I capability 是协议能力，不要求探针模型就是本包模型。不强求非空框，非空算法另有逻辑测试；不事后放宽容差。成功须完整树退出及 receipt，然后 intent → 同卷 rename → 短事务 Artifact 登记与成功 CAS。取消抢先不发布，缺 receipt 停领，孤儿不自动恢复为成功；无自动重跑。下载按资源 ID 鉴权，同一已验证 fd 有界流式传输，损坏返回 409。

新增闭集 PACKAGE_SOURCE_CHANGED / PACKAGE_RUNTIME_CHANGED / PACKAGE_BUNDLE_INVALID / PACKAGE_VALIDATION_FAILED / PACKAGE_STORAGE_FAILED；权限/归档/取消/幂等冲突沿用现有规范。重试来源身份和前端恢复记录按用户+项目分区，不因刷新/超时产生新任务。

## 6. 放行与验收

分阶段：契约与纯构建 → 独立 runner → 服务/受管发布 → UI → 精确 SHA 普通回归及原生独立验收。实现完之前仍501；接线后能力默认不可用，只有独立 package probe 在同一 worker.lock 下通过并绑定模板/core/lock/runtime 才 available。probe 复用共享恢复，失效先置 false；API只做轻量记录核验，不执行 ML。不得用源码标志或 I available 直接宣称 P available。

隔离验收在联网准备阶段使用已有官方 hash-pinned wheel，执行阶段禁网、非 root、无宿主挂载、资源有界，不能扩大现有安全设置。提取 ZIP 到新目录，以不含 backend/app、FastAPI、Torch 的独立 venv 执行，清空 PYTHONPATH，用 import guard 和包目录检查证明无平台依赖；在闭集匿名报告中新增 P 阶段，不沿用 schema3 十阶段完整通过作为 P 通过。测试安装/运行步骤和清理均有退出证据，不发布模型或原始日志。

必要负向：清单 extra/重复键/非有限数/布尔冒整数；ZIP traversal/重复/链接/超限；每成员被改与校验后替换；跨项目/归档/禁用会话/CSRF；源变更/缺父来源；幂等丢响应/刷新；取消 GO前后/完成竞态/Worker丢失/缺receipt/rename窗口；缺依赖/错版本/provider/坏模型/坏图/恶意输出目标；许可成员缺失；旧探针失效。完整 T030/T040/T050/E/I 回归必须通过，新增 P 原生证据不能覆盖未测平台或完整故障矩阵。

## 7. 当前具体开放项

没有必须等待用户选型的架构问题。实施前需工程核验：依赖子集在当前准备镜像能否形成真正独立 venv、模型再分发条款的准确来源、历史 deployment_zip 是否存在。分别由锁闭包/隔离测试、许可清单、只读数据核查解决；失败仅阻断相应验收/发行。P 分阶段实现中，尚未验收。

独立运行验收必须比较同一输入的完整 raw tensor（atol=1e-4、rtol=1e-4）以及 detections（IoU≥0.99、score差≤0.001、坐标差≤0.5px）；不能以空检测列表相等替代 raw 验证。CLI 不公开写出 raw，内部执行函数仅供验收比较。
