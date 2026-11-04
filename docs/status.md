# 项目状态 · T020 accepted / T030 review_required（2026-11-04 UTC）

T020 身份与项目最小闭环已通过独立代码/安全审查，并在提交 `cc2e66043473b9d3f432319fab41130cab3f2270` 的 [GitHub Actions 41779814303](https://github.com/TudouXiang/edgevision-training/actions/runs/41779814303) 完成真实 Chromium 验证。T020 **accepted（Linux CI 范围）**。T030 已形成候选：真实受限 ZIP staging/pending 版本、纯校验服务、owner-aware 查询、ready-only 有界框预览及基础前端；复用 0002，无迁移。当前 **review_required**，本机 34 项 T030 定向测试与完整后端/前端/契约检查待以最终报告为准，真实 Chromium 新场景仍须 GitHub CI。

现有候选能力增加数据集上传/列表/不可变版本与受限预览；pending 不可预览/训练，`/check` 仍明确 501，完整 Worker 接线属 T040。Windows 新功能、实际 TLS、人工视觉/截图、多进程压力及后续训练/模型/部署仍未验收。历史本地 Chromium 不可启动的结论保持有效；T030 浏览器仅完成 Playwright 发现，真实执行待受信 CI。远端 main 已由外部 PR 合并 T020 到 `f6db48a68534a93a50110e09750243e39417df7f`；其源码树与本工作树基线 `56c34f2ccc3d2dea46360c450079f373437f5e8f` 相同，T030 尚未提交/合并。

## 历史 Windows T010 验收（2026-09-29）

Windows 本机已对项目级后端依赖同步/核对（26 个已安装包无需更改），并完成隔离空库重复迁移、代表性 `0001` 一致性副本升级、OpenAPI/TS 生成与漂移检查、真实 API/Worker/Web HTTP、浏览器窄屏/键盘/刷新/断线检查。修复独立审查发现的 `cancelling→failed` 守卫漏项后，原样 `bash scripts/dev.sh check` 退出 0：纯契约 6 项、脚本/Worker 9 项、pytest 20 passed、前端 build 和 contract-check 通过。A01–A04 **PASS**；独立 [`change-review`](evidence/T010-change-review-2026-09-29.md) 结论 `accept`，T010/M1 **accepted**，T020 **ready**。原始命令、退出码、数据/代码指纹和边界见 [`Windows 复核报告`](evidence/T010-review-2026-09-29.md)。`backend/uv.lock` 和生成契约已在本机 Git 基线。真实旧用户库迁移、ML/ONNX/RKNN、真任务进程树仍未执行。

## 历史 Linux 工作区记录

以下表格和命令结论属于 2026-09-23 至 09-28 的 Linux 隔离工作区，当时的 FastAPI/迁移/Windows 未执行结论仍保留作原始证据，当前本机结果以上述 Windows 报告为准。Linux 跨平台入口记录见 `docs/evidence/portable-bootstrap-2026-09-28.md`，地基报告见 `docs/evidence/foundation-report.md`。

| 模块 | 源码存在 | 本轮实际构建/运行 | 真实业务后端接入 | 验收 |
| --- | --- | --- | --- | --- |
| 旧 Next.js 原型 reference/ | 是，原件不改 | 本轮未重试；历史离线安装失败 | 否，仍有硬编码和计时成功 | 不可作为正式产品 |
| Vue3/npm/Vite 工作台 web/ | 是，保留原视觉并新增阶段路由 | npm 安装、类型检查/Vite 构建退出 0；隔离 HTTP / 和 /training 均 200 | 仅健康接口请求代码；本轮未连接实际 FastAPI | 浏览器截图/真实 API 交互 NOT_RUN |
| FastAPI 接口与 Pydantic DTO | 是，明示 501/422/404 规则 | 5 项纯契约测试通过、Python 语法编译退出 0；当前容器缺 FastAPI，HTTP 未启动 | 业务均占位 501（运行时未测） | A01、A04 NOT_RUN |
| Alembic 0001 + 新 0002 / SQLAlchemy Models | 是，0001 原样；0002 候选 | 语法检查通过；实际迁移/pytest 未运行 | 无 | A02 NOT_RUN，旧库不可直接升级 |
| Worker/状态协议 | 是，单实例和子进程占位 | 隔离最小测试表：一个 UNSUPPORTED_JOB 失败、第二个 queued；遗留 running 时退出 4 且不改状态 | 没有训练/导出 runner | 仅失败闭环烟测，进程恢复 T040 |
| OpenAPI/前端生成类型 | 生成脚本及本地 CLI 已有；生成产物无 | contract-generate 退出 2（缺 FastAPI） | 旧健康 TS 为明确临时桥接 | A03 未通过、生成与漂移检查待补 |
| 项目 4 Skill/AGENTS | 已逐项合并；保留明确触发/输入/输出/停止与参考文件 | 静态路径/格式检查通过；本宿主为手动读流程 | 不适用 | 自动发现/其他宿主未验收 |
| Ultralytics/PT/ONNX/RKNN | 无正式适配器与真实资产 | 未执行训练、模型导出、推理或硬件实验 | 无 | 全部未验收 |

## 技术与任务基线

单机双角色，Vue3/TS/Element Plus + FastAPI/Pydantic/SQLAlchemy/Alembic/SQLite，本地文件，独立 Worker/每任务子进程/单重任务槽，轮询日志；ONNX 部署主线、PT 与 ONNX 单图推理分别实跑、RKNN 扩展边界。新启动包 docs/contracts.md 规定公共语义，候选精确 Schema 为 backend/app/schemas.py；ADR 0005 记录与先前 SSE/状态/URL 的差异。旧 T0–T9 草案在 docs/tasks/legacy-tasks.md，现行任务为 docs/tasks/T000–T070。

## 待审查与领取闸门

1. T030 候选须完成独立代码/数据安全审查，并在候选提交的 GitHub 托管 runner 上实际执行新增 Chromium 场景；在取得对应提交证据前不能写 accepted，T040 不自动进入。
2. 真实旧用户 `0001` 库若将来提供，先停 API/Worker、备份并在一致性副本验证；本轮仅有代表性隔离样本。项目级后端同步没有重装已存在的 26 个包，已有环境的可运行性与全新环境可重装性分开判断。
3. T040 前分别在 Linux/Windows 验证真实任务进程树取消、重启和恢复；不得以占位 Worker 的路径替代。
4. 核查学校是否把 NPU/边缘实机作为正式硬性要求、目标机器容量与可信数据/权重许可。无授权不下载模型或开始训练。

T000 的历史盘点仍标 `review_required/ML_CHECK_PENDING`，不阻塞轻量 M1；T010 **accepted**，T020 **accepted**，T030 **review_required**。T040 不自动放行；ML、ONNX、RKNN 和真实训练均未因 T030 执行。
