# 文档导航

先读[项目状态](status.md)与[V1 范围](scope.md)，再按目的选择下面的文档。状态与验收结论需要对应分支、精确提交和实际证据；设计、任务清单或源码存在不代表功能已验收。

## 安装、使用与开发

| 目的 | 入口 |
| --- | --- |
| 安装依赖、初始化、启动 API / Worker / Web | [仓库 README](../README.md) |
| 查看阶段、前置条件与任务单 | [任务索引](tasks/README.md) |
| 准备修改、运行检查与提交审查 | [贡献指南](../CONTRIBUTING.md) |
| 理解组件、进程与恢复边界 | [架构](architecture.md) |
| 理解页面和交互的设计约束 | [界面设计](ui-design.md) |
| 核对实现规则与项目 Skill | [AGENTS.md](../AGENTS.md) |

## 契约与数据

| 主题 | 入口 |
| --- | --- |
| 公共语义、状态机、幂等、权限和模型边界 | [核心契约](contracts.md) |
| HTTP 路径及阶段增量 | [API 说明](api.md) |
| 数据库模型与文件边界 | [Schema](schema.md)、[本地存储](storage.md) |
| 预处理、输出和模型信息 | [模型元数据](model-metadata.md) |
| 机器可读 API 与前端类型 | [OpenAPI](../contracts/openapi.json)、[生成的 TypeScript](../contracts/generated/openapi.ts) |

公共类型由后端 Pydantic / FastAPI 生成。不要手改生成文件；生成与漂移检查命令见仓库 README。说明文档保留的历史阶段描述不能覆盖[最新状态](status.md)与对应提交的生成契约。

## 验收与证据

- [验收矩阵](acceptance.md)：A01–A16 的条件、阶段闸门和历史编号边界。
- [证据导航](evidence/README.md)：各阶段验收、实现报告、源码检查及失败历史。
- [项目状态](status.md)：先看顶部的最新结论；下方按日期保留的记录属于各自历史版本。

## 关键架构决策

| 决策 | 入口 |
| --- | --- |
| 单机范围、原型隔离、轮询与 ONNX 主线 | [0001](adr/0001-single-host.md)、[0002](adr/0002-ui-prototype.md)、[0003](adr/0003-events.md)、[0004](adr/0004-onnx-first.md) |
| 地基契约与跨平台开发 | [0005](adr/0005-foundation-alignment.md)、[0006](adr/0006-portable-development.md) |
| 会话身份、受控数据集、受管 Worker | [0007](adr/0007-t020-session-auth.md)、[0008](adr/0008-t030-controlled-datasets.md)、[0009](adr/0009-t040-managed-worker.md) |
| 许可与固定训练适配器 | [0010](adr/0010-project-licensing.md)、[0011](adr/0011-t050-fixed-training-adapter.md) |
| T060 重建安全与导出契约 | [0012](adr/0012-t060-rebuild-safety.md)、[0013](adr/0013-t060-export-rebuild.md) |

## 历史与来源

- [环境盘点](environment.md)含早期工作区观察及后续浏览器报告规范，不能当作当前机器的安装结果。
- [Windows 接手记录](CODEX-HANDOFF.md)是 2026-09-28 / 09-29 的历史快照。
- [旧任务草案](tasks/legacy-tasks.md)仅供追溯，不再作为当前验收依据。
- [项目许可范围](../LICENSE_SCOPE.md)与[第三方声明](../THIRD_PARTY_NOTICES.md)区分原创内容、依赖、参考原型和训练资产。历史参考 ZIP 保持原样，不是产品前端或验收证据。
