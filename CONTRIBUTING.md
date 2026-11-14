# 贡献与变更检查

本项目采用单机、双角色、单重任务槽的目标检测平台范围。开始前阅读 [AGENTS.md](AGENTS.md)、[项目状态](docs/status.md)、[范围](docs/scope.md)、[架构](docs/architecture.md)、[核心契约](docs/contracts.md)，再选择[已放行的任务](docs/tasks/README.md)。更多入口见[文档导航](docs/README.md)。

## 保持改动边界

- 一个任务使用独立分支；一个 worktree 同时只有一个写入者。并行工作分别使用 worktree、数据库、运行目录和端口，不覆盖未提交改动。
- 修改前查看 `git status --short` 与当前提交，确认基线。不要默认 stash、reset、clean、改写历史或处理他人的分支。
- 保留现有 `backend/`、`web/`、`contracts/`、`scripts/` 的职责。涉及范围、存储、状态机或公共接口的变更，先记录影响、最小方案和迁移 / 回退办法，再更新相应 ADR 与契约。
- 文档导航修复不改变阶段验收结论。任务状态必须有对应实际证据；普通 CI 不能放行未执行的 ML、ONNX 或硬件能力。

## 本地检查

安装、系统前置条件和 Linux / Windows 启动步骤以[仓库 README](README.md)为准。依赖仅安装在项目隔离环境，沿用 `backend/uv.lock` 与 `web/package-lock.json`；不自动更换包管理器或安装系统软件。

在仓库根目录执行：

```bash
python3 scripts/dev.py doctor
python3 scripts/dev.py check
```

Windows PowerShell 使用相同入口：

```powershell
py -3 scripts\dev.py doctor
py -3 scripts\dev.py check
```

`check` 包含纯契约 / 脚本测试、后端 pytest、前端单元测试与构建、契约漂移检查。它不代表真实模型或完整浏览器验收。

仅检查文档既有范围约束，可运行：

```bash
backend/.venv/bin/python -m pytest backend/tests/test_docs_scope.py
```

Windows 对应命令为 `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_docs_scope.py`。该测试目前覆盖 README 与验收文档的部分链接和范围措辞；新增导航、任务或证据索引中的相对链接仍须逐项核对。

### 契约改动

后端 Pydantic / FastAPI 是公共类型来源。修改源码后使用 `python3 scripts/dev.py contract-generate` 生成，再以 `python3 scripts/dev.py contract-check` 检查；Windows 替换为上述 `py -3 scripts\dev.py` 入口。不要手改 `contracts/openapi.json` 或 `contracts/generated/openapi.ts` 来消除类型错误。

### 真实运行验证

普通浏览器回归使用 `scripts/e2e.py` 创建的临时数据库与受控服务，准备和执行步骤见仓库 README；`--list` 只证明测试发现与编排，不算浏览器通过。

真实 ML、模型下载、隔离验证及正式实验须单独确认来源、许可、预算和授权。普通 push / PR 不自动触发真实 ML；不要更改工作流门控或写入伪造能力记录来跳过验证。不得用用户正在使用的数据库、服务或数据目录做测试。

## 记录与审查

- 为实际执行的检查记录命令、退出码、环境、精确源码提交及未提交差异。区分通过、失败、跳过和未执行，说明后者的原因。
- 依据任务覆盖权限、失败、取消、恢复、产物完整性等相关分支；不相关项写明不适用，不为文档修改宣称业务回归通过。
- [验收矩阵](docs/acceptance.md)定义条件，[证据导航](docs/evidence/README.md)定位报告。原始证据保留；更正追加说明，不改写过去的测试结果。
- 项目 Skill 在 `.agents/skills/`。按任务读取相应 `SKILL.md`；未自动发现时明确手动执行，格式检查不等于 Skill 已触发。
- 提交前检查差异与 `git diff --check`，只暂存本任务文件。PR 说明任务、影响、验证、证据与剩余阻塞；实现先进入 review_required，不提前标 accepted。
- 按任务授权决定是否推送或创建 PR，不因本指南或模板自动发布、合并或部署。

## 提交内容与许可

不提交 `.env`、密钥、凭据、数据库、用户数据、模型权重、依赖环境或原始敏感日志。公开证据仅保留必要脱敏内容；不要公开用户机器绝对路径。参考 ZIP 保持原样，不能当作正式产品或测试证据。

原创内容与第三方内容的边界见 [LICENSE](LICENSE)、[LICENSE_SCOPE.md](LICENSE_SCOPE.md) 和 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。新增依赖、数据或资产须核对各自许可，不能以项目许可证替代第三方授权。
