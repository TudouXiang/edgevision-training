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

## 待执行

API/Worker/前端启动和本机普通浏览器验证仍待逐项证据。当前不能称常驻服务已运行。正式数据实验、用户机 ML probe/训练/导出/推理/包执行未验收。
