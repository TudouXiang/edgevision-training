# 地基阶段报告 · T000 / T010（待审查）

日期：2026-09-23 UTC。执行宿主：当前隔离工作空间 Ubuntu 24.04.3；实际项目 /workspace/scratch/be544824c543，Git main 基线 57920e6，无远端。用户个人电脑曾展示旧版 uv 同步、0001 迁移和 Uvicorn 日志，**不能替代当前 0002 的执行证据**。本报告所述新版改动均待独立审查，不等于 accepted。

## 输入与资产复用

启动包 upload/edgevision-foundation(1).zip 的 SHA-256 为 da1568e9b63239916ff3a3fc7e83942f291493c960a635d495f0a9be105ee0dc；隔离提取并对包内 SHA256SUMS 逐条校验均 OK。开始改动前 Git 仅该上传目录未跟踪；未对用户数据、他人仓库或原型 ZIP 写入。START-HERE、prompt 01、已有 AGENTS/Git 与包内 scope/architecture/contracts/status/environment/T000/T010/acceptance 按序核对，逐文件差异与工具明细见 T000-report.md。

复用：原有 Vue3/TypeScript/Element Plus 视觉和 npm 锁文件、健康页、Vite、Python 健康检查和 501 路由基础、独立 Worker/子进程入口、0001_initial、历史原型留档。前端用 vue-router 增加 URL 路由，设计未重写。现有四个仓库 Skill 属同项目，逐一合并包内规则并新增 references/ 和 agents/，保留明确触发/输入/输出/停止。Skill 自动发现本宿主未得到证据，采用手动读取；其他模型宿主未验。

| 合并对象 | 新版位置与决定 |
| --- | --- |
| 规则、设计、任务 | AGENTS.md、docs/scope.md、architecture.md、contracts.md、api.md、schema.md、storage.md、model-metadata.md、environment.md、acceptance.md、tasks/；旧 T0–T9 草案移至 tasks/legacy-tasks.md；ADR 0005 记录差异 |
| 任务与进程 | backend/app/contracts.py 单一枚举/转移守卫；worker.py 未知遗留任务停领、占位执行只失败；runner_protocol.py 无正式或 Fake runner |
| 精确类型与 HTTP | backend/app/schemas.py 严格 kind 参数、范围、分页/游标、响应；main.py 现有健康路由与明示 501、统一 422；FastAPI app.openapi() 为生成源 |
| 数据 | backend/app/models.py 和新 alembic/versions/0002_foundation.py；旧 0001 不变，0002 两阶段迁移旧枚举并加 run/boot/child/版本字段 |
| 前端/契约生成 | web/src/router.ts、现有 App.vue 小改、openapi-typescript@7.13.0；scripts/export_contract.py 设计生成 OpenAPI/TS 与漂移检查；旧 contracts/api.ts 仅健康状态临时桥接，待真实生成替换 |
| 入口与测试 | scripts/dev.sh、scripts/doctor.py、backend/tests/test_contracts_unit.py、扩展 bootstrap 集成测试；数据及运行目录不入 Git |

包默认 pnpm 改用现有可用 npm；旧 ADR 0003 SSE 在首版被轮询替代；旧恢复的 failed/INTERRUPTED 变为独立 interrupted，未经进程身份核对不自动改写旧行；旧 0001 不修改。PT 和 ONNX 分别真实推理的范围补充留待 T060，RKNN 仍不可用。影响、理由及迁移风险见 ADR 0005。

## 冻结的开发命令

以下入口**已写入代码**，只按下表声称实际运行的部分：

| 命令 | 作用及前置 |
| --- | --- |
| bash scripts/dev.sh doctor | 只读列出环境、依赖可见性；实际运行退出 0 |
| cd backend && uv sync --extra dev；cd ../web && npm ci | 项目局部安装；前端依赖本轮用 npm install 执行，后端本容器离线不可获取 |
| bash scripts/dev.sh migrate | 需有后端依赖；仅先在空临时库/已有 0001 库副本执行；当前未执行 |
| bash scripts/dev.sh api、worker、web | 独立终端启动 API、Worker 和 Web；本轮只对 web 做了隔离启动/HTTP 检查 |
| bash scripts/dev.sh contract-generate | 从 app.openapi() 导出 contracts/openapi.json，再生成 contracts/generated/openapi.ts；本容器缺 FastAPI，退出 2，无生成文件 |
| bash scripts/dev.sh contract-check | 临时目录重生成并字节比对，不修改已提交文件；缺生成产物未执行 |
| bash scripts/dev.sh check | 纯契约测试→pytest→前端构建→契约比对；本轮前五项纯测试通过，pytest 缺失使总命令退出 2，后续步骤未执行 |

工具环境：Python 3.12.14、uv 0.12.17、Node 24.19.0、npm 11.9.0；前端 npm ls --depth=0 实得 Vue 3.5.43、Element Plus 2.14.6、vue-router 4.6.4、Vite 7.3.6、TypeScript 5.9.3、openapi-typescript 7.13.0。当前容器 FastAPI/SQLAlchemy/Alembic/pytest 不存在；后端没有 uv.lock，版本组合和 API OpenAPI 尚未在该环境核定。Torch/Ultralytics/ONNX/ORT/GPU/NPU 均没有真实可用性证据，可信数据和权重未提供。没有系统级安装、未下载模型、未运行训练、未触发付费资源。

## 实际命令、退出码及验证层级

| 检查 | 退出码/真实输出 | 结论 |
| --- | --- | --- |
| sha256sum -c SHA256SUMS（隔离提取的包） | 0；包内每项 OK | 输入完整性 PASS |
| uv sync --offline --extra dev | 1；FastAPI 不在本地缓存 | 后端依赖阻塞；不能据此断言用户电脑不可用 |
| npm install vue-router@4 与 npm install --save-dev openapi-typescript@7 | 0；仅项目本地 node_modules/锁文件 | 前端依赖可取得 |
| npm ls --depth=0 | 0；上述精确版本 | 安装可见，不证明浏览器交互 |
| npm run build | 0；Vue 类型检查+Vite v7.3.6，CSS 48.95 kB、JS 167.39 kB | 前端构建 PASS |
| 隔离启动 Vite、同一网络命名空间 urllib 请求 / 和 /training | 0；两条均 HTTP 200，返回工作台 HTML | 页面服务/深链 fallback 最小检查 PASS；未做浏览器视觉 |
| PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p test_contracts_unit.py | 0；5 项通过：取消与成功竞争、遗留中断证明、kind/参数上限、空更新/未知字段、空 data root | 纯 Pydantic/状态守卫 PASS，不证明 FastAPI/SQLAlchemy |
| Python TypeAdapter(JobCreate/JobPublic/DatasetPublic/Incremental/CapabilitiesResponse).json_schema() | 0；生成局部 JSON Schema 成功 | Pydantic Schema 可形成，不等于 FastAPI OpenAPI |
| python3 -m compileall -q backend scripts、bash -n scripts/dev.sh、git diff --check | 均 0 | 语法与空白检查 PASS，迁移运行仍未证实 |
| 临时最小 SQLite 表运行 python -m app.worker --once 两次 | 脚本 0；第一轮首 job failed/UNSUPPORTED_JOB、第二 job queued、事件数 2；新增 orphan 后 Worker 退出 4、原 running 保留 | 负向占位/停领路径实际运行；表为手工测试夹具，**不是 Alembic 迁移** |
| bash scripts/dev.sh contract-generate | 2；Missing project-local Python dependency: fastapi；无生成产物 | 生成未完成，未宣称 A03 PASS |
| bash scripts/dev.sh check | 2；5 项纯测试通过后 Failed to spawn pytest | 整体检查 FAIL（依赖阻塞），后续前端/契约步骤该次未执行，前端另有独立构建证据 |
| 实际 Alembic 两次升级、FastAPI HTTP、pytest、GPU/ML、浏览器截图 | NOT_RUN | 不能据旧报告或代码存在判 PASS |

## A01–A04 验收矩阵

| ID | 状态 | 已见证据与尚缺步骤 |
| --- | --- | --- |
| A01 轻量启动 | NOT_RUN | doctor 和纯 DTO 测试通过；新版 FastAPI 在本容器缺依赖，API HTTP 未启动，ML 能力响应未请求 |
| A02 迁移 | NOT_RUN | 0002 源码/Models 已写且编译；空库+旧 0001 副本升级两次、外键和约束检查未执行；不可在唯一用户库上试 |
| A03 契约生成 | FAIL（环境阻塞） | Pydantic 枚举/参数及 JSON Schema 测试通过；contract-generate 实际退出 2，OpenAPI/TS 产物与漂移检查都未完成 |
| A04 空态/未实现 | NOT_RUN | Vue 构建及本机 HTML 200；浏览器视觉、实际 FastAPI 501/422/404 与前后端同源联调未执行；页面从真实健康接口请求，无随机业务计时器 |

T010 的文件、受限协议与开发入口已具备可审查形态，但 M1 **不满足**“A01–A04 全通过”。后端迁移特别需要在副本上实跑；生成 TS 前旧健康手写类型只是过渡。用户本地旧版日志可作为旧版启动反馈，不属于本代码/迁移验收。后续在有依赖的目标环境补齐 uv.lock、迁移/pytest/生成/浏览器证据，按 change-review 审查后才能放行 T020；本轮不进入 T020。

任务状态：review_required（伴随环境阻塞和明确 NOT_RUN/FAIL），T020 blocked。学校硬性 NPU/正式题目、可信资产与目标硬件仍需用户后续核对，不妨碍对当前代码和文档开展只读审查。
