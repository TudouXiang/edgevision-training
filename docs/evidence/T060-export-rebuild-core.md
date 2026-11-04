# T060 E 后端重建证据（2026-11-04 UTC）

状态：源码候选，轻量审查中；**真实 ONNX/ORT、训练、HTTP ML、浏览器 ML、容器隔离运行全部 NOT_RUN**。
以公开 T050 与 ADR 0012/0013 为基础重新编写，不沿用丢失的未发布候选或它的计数。

## 实现边界

严格导出 DTO/输入/evidence/公开判别联合；同项目 succeeded train/passed PT 与原发布绑定；数据报告、完整数据清单、原 PT 三边界重复检查；固定 CPU 导出/递归图约束/原始图 bytes checker+ORT/三个张量容差；共享 Worker/guardian/探针锁与恢复；完整束 intent/rename/CAS；鉴权且同描述符有界下载。

API/Worker 不导入 ML。正式 runner 无测试模式、无外部 PT/路径/URL、无随机成功、无 PT fallback。I/P 继续 501。
完整联合依赖锁由集成任务单独核验；文件不存在、环境版本不符或能力探针陈旧时保持不可用。

## 已执行与待执行

- 编辑前按 AGENTS 手动读取 arch-spec、feature-delivery、experiment-evidence；本环境不宣称 Skill 自动触发。
- 轻量导入命令：`PYTHONPATH=backend <轻量项目解释器> -c "import app.main,app.worker,sys; assert not {'torch','onnx','onnxruntime','ultralytics'}.intersection(sys.modules)"`，退出 0。
- 首批 `pytest tests/test_export.py -q`：39 passed，退出 0。随后扩展的同命令：55 passed，退出 0；只包含 mock/纯逻辑/普通 Python 受管进程，不是模型运行。
- 55 项包括权限/归档/幂等、源任务状态、源/报告/数据损坏、缺输出/错 hash/错绑定、递归外部/稀疏/custom 图对象、128MiB 解析前边界、取消 pre-GO/运行/rename、CAS 回滚、Worker loss/no output、严格 union、鉴权下载及轻量导入。
- 后续完整轻量回归与最终文件指纹另行补记；以上计数只对应各次已执行代码，不提前称最终全部通过。
- OpenAPI/TypeScript 由真实 Pydantic/FastAPI 生成成功，复用只读项目级 openapi-typescript，未手改生成文件。
- `training_http_probe.py`、`export_http_probe.py`、`test_onnx_runtime_policy.py` 新协议源码已准备，**未执行**。显式原生测试仅在授权的隔离边界中启用；普通轻量环境两项 policy opt-in 均为空。

本地检查用现有轻量 venv，自己的临时数据库/目录/进程；没有安装或导入 ML、下载权重、运行 Docker、访问外部遥测或触发远端 CI。运行中的私有 IDs/hash/log/模型不入 Git。

## 仍需补证

固定联合工具链安装与实际原始图 IR8、checker/ORT/三个张量容差；原生缺依赖/坏图/外部文件/custom/sparse/数值偏差/no-fallback 负测；真实 HTTP 管理链和浏览器；独立审查；跨平台新增 E 行为。E 未 accepted，I/P 未实现，不因受管进程 fixture 通过而声称模型导出通过。

## 后续轻量回归与审查修正

- 第一轮全量：204 passed、9 skipped，另有 2 项失败。原因分别为本 worktree 缺少已安装 TypeScript 生成器的路径，以及旧“不支持任务”测试仍使用现在已实现的 export_onnx。前者复用现有项目级只读 node_modules，后者改为仍未实现的 package，未削弱业务失败断言。
- 修正后全量：`EDGEVISION_ML_POLICY_ROOT= EDGEVISION_ONNX_POLICY_ROOT= PYTHONPATH=. <轻量解释器> -m pytest -q`，退出 0，213 passed、9 skipped、8 subtests passed。9 个 skip 是 3 个训练原生策略用例及 6 个 ONNX 原生策略用例，不能算原生通过。
- 随后补强探针异常控制流与固定标量类型，完整 E focused suite 68 passed，退出 0；契约漂移检查退出 0。
- 独立审查指出长文件 hash 不能占有 SQLite 唯一 writer。发布和提交已改为在只读快照中验证字节/环境，最终 writer 内仅比较少量不可变数据库行、重新鉴权/归档/幂等检查和 CAS/插入，不再读文件或导入运行时。
- 新并发延迟测试（发布 hash 阶段可及时取消；提交 hash 阶段允许其它写入并最终识别归档/禁用/会话撤销/源状态变化）连同相关关键回归 8 passed，退出 0。最后代码还需集成后的全量回归与独立审查，不能把前一轮计数直接迁移。

## 最终后端轻量复核

`7dd74a0` 全量轻量回归退出 0：**224 passed、9 skipped、8 subtests passed**，228.49 秒；其中新增 E 为 73 项。包含上述锁范围/权限重查修正。独立静态复审已由集成任务进行，原 writer-lock 阻塞项已解除。
最后又把“能力检查后发行包消失”和“最终事务前源记录消失”两种竞态规范化为 `409 EXPORT_INPUT_UNAVAILABLE`，不留下新 Job；对应 2 项 focused 测试退出 0。这两项不冒充此前全量运行的一部分，需由最终集成补跑。

所有 native 检查依然 NOT_RUN；9 个 skip 保留，未为获取绿色而启用任何 ML。契约生成/漂移、Python AST 解析和 Git whitespace 检查均通过；最终不包含私有运行产物。
