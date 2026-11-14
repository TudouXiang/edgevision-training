# Linux CPU 完整链路运行与演示手册

这是可复现操作说明，不是本机已安装或已部署的证明。精确已执行版本见 `evidence/`；Windows 进程测试不等于 Windows ML。当前模型范围是可信 YOLO11n、静态单图检测、CPU。RKNN/NPU、视频、远程设备不在已实现范围。

## 1. 准备与数据保护

- 使用独立 checkout 和独立数据目录，不覆盖已有工程、数据库、模型或虚拟环境。升级先停止本项目 API/Worker，并按一致性备份流程保留数据库及其引用文件；不要只复制正在写入的 SQLite 主文件。
- 联合模型环境要求 Linux x86_64、CPython 3.12；独立包还要求兼容 glibc >= 2.28。Node 版本须满足仓库 `web/package.json`。
- 依赖和资产准备需要网络、磁盘和时间。不要在公司/用户数据上试错。原生运行中的 Python 审计不是通用 OS 网络沙箱；CI 的断网容器证明不能被描述成本机隔离已自动配置。
- 所有终端必须设置相同的绝对 `PLATFORM_DATA_ROOT`。使用不与已有服务冲突的端口，保持浏览器与 API 同源代理。默认仅监听回环地址；不要为演示关闭安全设置或暴露服务到公网。

在仓库根目录先按 README 安装轻量项目依赖、迁移并交互创建管理员；无默认账号/密码。数据目录变量由操作者设置，不把密码放入命令行或文档。

## 2. 训练、导出与独立包环境

以下操作仅在全新的、目标平台匹配的项目环境执行：

```bash
python3.12 scripts/install_ml.py --delivery --check
python3.12 scripts/install_ml.py --delivery
python3.12 scripts/install_package.py --check
python3.12 scripts/install_package.py
```

两个安装器必须由**同一个基础 CPython 可执行文件**运行，不仅是都显示“3.12”；包启动会核对基础解释器字节与 `pyvenv.cfg`。`--check` 只检查计划，不表示安装或模型验证成功。

前两步使用 `backend/.venv-delivery` 的锁定联合 CPU 环境；后两步建立独立九依赖 `backend/.venv-package`。不复用后台依赖来证明包独立，不手工改 lock 或跳过 hash/RECORD 检查。已有环境不兼容时另建 checkout 排查，不删除用户环境。

固定基础权重只通过仓库受控下载器获取并核验，不接受任意外部 PT：

```bash
python3 scripts/fetch_training_asset.py --output /absolute/private/yolo11n.pt
```

先停止本项目 Worker，确认受管任务正常终结，进入 `backend/`，使用联合解释器建立实际环境证明：

```bash
.venv-delivery/bin/python -m app.training_probe --asset /absolute/private/yolo11n.pt
.venv-delivery/bin/python -m app.export_probe
```

每条命令必须退出 0。失败时能力保持关闭；不要复制 CI capability JSON，不删运行身份/锁来强行放行。恢复必须按受管进程证据核对，不能凭旧 PID 杀未知进程。

## 3. 启动与演示前半段

README 的轻量 `scripts/dev.py api/worker` 仅供前期启动检查；从本节起先停止这些本项目实例，改用联合解释器，不能同时启动两套 API/Worker。

在 `backend/` 分别开终端启动 API 和 Worker，使用相同数据目录及联合解释器：

```bash
.venv-delivery/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
.venv-delivery/bin/python -m app.worker
```

Web 按 README 启动，访问 `http://127.0.0.1:5173/`。若改端口，同步代理与允许的 Origin，不扩大到任意来源。

演示步骤：
1. 管理员登录，创建普通用户；普通用户登录并创建自己的项目。
2. 上传合法 YOLO ZIP，点“开始校验”；等待 ready，查看真实校验报告与有限标注预览。失败就展示错误，不称上传即训练成功。
3. 选择 ready 快照，以 CPU、1 epoch 小规模验证链路；等真实终态，读取最终日志/指标并下载 best/last。记录数据版本、模型摘要、任务参数和运行环境。
4. 选择可信训练产物进行 ONNX 导出；只有 checker 和 ORT 真正通过的产物才作为后续输入。保存平台返回的 ONNX Artifact UUID，UUID 不是文件路径。
5. 如需基础实验对比，再创建一项真实训练，选两项成功任务比较参数/来源/指标。不同数据或环境不直接排名；训练指标不是独立测试集报告。

## 4. 建立推理与部署包能力

有成功 ONNX Artifact 后停止本项目 Worker，确认无活动任务。仍在 `backend/` 且同一数据目录执行（把占位值换为该项目真实 UUID）：

```bash
.venv-delivery/bin/python -m app.inference_probe --onnx-artifact-id ONNX_ARTIFACT_UUID
.venv-delivery/bin/python -m app.package_probe --onnx-artifact-id ONNX_ARTIFACT_UUID
```

推理 probe 同时验证可信 PT/ONNX 链；包 probe 验证独立运行环境和模板。全部成功后重启同一个 Worker，并在界面刷新能力状态。不使用手写“已验证”标志。

随后上传合法单图，选 PT 或 ONNX 后端，等待真实任务完成并查看结果；选择可信 ONNX 创建部署包，等待 succeeded 后下载 ZIP。管理员可从全局任务查看/请求取消；`cancelling` 不是“已停止”，须再读终态。

## 5. 离开平台运行包

部署 ZIP 是**源码包**，含 ONNX、运行脚本、推理核心、固定示例、清单、依赖锁及许可说明，不含 Python/wheels。先读包内 README 与许可说明，在支持的干净目标环境准备独立 CPython 3.12 虚拟环境，按包内 hash lock 安装依赖。首次安装需要网络，或自行准备完整兼容 wheelhouse；不能称下载即离线运行。

在解开的包目录中，用目标环境的 Python 执行包内示例命令：

```bash
python -I run.py --image example.png --format png --output fresh-results
```

输出目录必须不存在；成功产生 `result.json` 与 `preview.png`。失败可能保留部分输出，先检查再人工处理，不自动覆盖。执行不需要启动平台 API/Worker，也不导入平台包。

每个下载产物的声明是完整性验证，`standalone_execution=not_run_for_this_artifact`；CI 对固定候选模板的独立运行证明不等于每个未来模型包都运行过，更不等于模型精度达标。

## 6. 交付验收清单

- 记录 commit/tree、系统/解释器、安装与 probe 退出码；数据及模型来源、hash、许可清楚。
- 登录、用户隔离、上传/校验、训练、导出、推理、包下载及独立执行逐项 PASS/FAIL/NOT_RUN。
- 刷新、断网恢复、取消、服务重启分别记录；不要将进程夹具等同整机掉电验证。
- 正式实验另行冻结数据划分、预处理/阈值、计时与预算；原始结果保留，不能从合成烟测外推准确率或 NPU 性能。
- 密码、会话、用户图片、数据库和模型不放到公开验收文档。演示材料只用获准公开的数据及脱敏摘要。
