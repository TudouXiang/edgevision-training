# T070 PEC003909 隔离部署记录（进行中）

这是本机执行记录，不是整项目验收。旧工作区、用户数据及既有服务不变；新源码准备与服务真正可用分开报告。

## 集成基线

远端 main 已在 #54 所需检查成功后以非 force、expected SHA 保护从 `ae3e83f1b70f29ce8fdd0c929a2a03f66fa11835` 快进到 `ba9ca8d4913f213259c389c35ff7681b2f92a923`，读回确认。合并提交 `bbb5900d1a4aa3f3b954c7a3a01a5e50184451ff` 的父提交为旧 main 与 `0a204d9`，产品树保持 #53 十二阶段通过版本；随后只增加六个文档。独立审查确认无历史丢失或产品差异。

[#54](https://github.com/TudouXiang/edgevision-training/actions/runs/43641018353)：checks 与 Windows success，866 后端 passed、14 原生 opt-in skipped、157 前端 passed、契约匹配、普通浏览器5 passed/1预期跳过。ML 为普通 push 预期 skipped；原生证据精确属于 [#53](T070-comparison-acceptance-2026-11-14.md)，不冒称 #54 原生运行。

## 只读前检及源码准备

- PEC003909：Linux x86_64、glibc 2.38、Python 3.12.13；16 逻辑核、RAM 15 GiB，检查时 available 6.3 GiB、swap 13/15 GiB 已用。磁盘约602 GiB可用。资源值为时点观察，不是长期保证；暂不在此机启动重模型训练。
- 系统 Node 20.15.1 不满足仓库 >=22.13。项目私有官方 Node 22.13 的校验文件可访问；不改系统 Node、网络或安全设置。
- 旧两个 checkout 均未改动；在全新部署目录接收源码 archive，不包含用户数据、环境依赖或模型。
- Archive 892072 bytes，SHA256 `c09c7b46864cdff4e985eb08e1aab53d59e2ac26b1c8fc964fc3b3ff66bee314`；375 个成员（337 文件、38目录），无链接/特殊文件/越界路径。
- 安全解压后重建 Git index 得到 tree `d6215f0d1f8b5b62142b52bd72cd76beee69883c`，与远端 ba9 一致。此处是源码树等价，本地空 HEAD 不包含远端提交历史，不伪造其身份。

## 已执行轻量准备

- 官方Node22.13最初安装后发现锁内abbrev/nopt要求更高版本，保留该目录但不作为最终运行时。改用官方校验的项目私有Node22.22.2/npm10.9.7；不改系统Node。再次npm ci退出0，无EBADENGINE警告。
- `python3 scripts/install_deps.py`退出0，独立backend/.venv安装32个轻量/dev依赖，web/node_modules按lock安装。
- `scripts/dev.py doctor`退出0；torch/Ultralytics/ONNX/ORT明确MISSING，未称模型能力可用。
- 全新隔离数据目录执行迁移成功；不读写旧工作区数据库。
- `npm run build`退出0，Vue类型检查及Vite构建成功。

## 本机普通浏览器实际验证

`python3 scripts/e2e.py --report-dir <独立证据目录>/ordinary-e2e`退出0。项目内固定Playwright 1.64.1 Chromium/FFmpeg准备完成；UOS被上游标为非官方支持且使用Ubuntu24.04 fallback，此次实际运行成功，无缺失共享库，不扩大为所有UOS版本支持承诺。未运行系统依赖安装。

Harness在自有临时DB、合成受控fixture和自动选择的回环端口上真实启动API/Worker/Web/浏览器，结束清理成功。匿名结果：discovered=6、executed=5、passed=5、expected_skipped=1、unexpected=0、flaky=0、reporter_errors=0、cleanup_status=passed。T020/T030/T040/T070普通用例实际执行；T050模型训练是明确的ML预期跳过，不计模型验证。

## 待执行

新隔离API/Worker/Web随后已实际启动，未配置系统自启。API回环8000健康HTTP200，返回数据库已迁移、存储可用；Web回环5173返回HTTP200。自有PID/进程组及日志保留于本机部署目录，未终止其它进程。首次管理员尚未初始化，没有代造/发送密码；页面实际渲染另待确认，不能仅凭HTTP200称可登录。正式数据实验、用户机 ML probe/训练/导出/推理/包执行未验收。

本机匿名Harness receipt SHA256：`a8a9733d80715a62ef929473be9e12d9ded9d9e70f4f6a5ee7b804cd0391cd5d`。准备摘要 SHA256：`362a6fd2316e46a79d8996c6509da1c3d2f104ee94eeec41b92e7b814d949999`。原始证据保留于本机独立部署目录；公开文档不包含账户、密码、截图或用户数据。
