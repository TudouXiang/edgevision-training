# T070 隔离集成审查

这是合并方案，不是已合入 main 的声明。

核对目标：main `ae3e83f1b70f29ce8fdd0c929a2a03f66fa11835`；功能候选 `213726fff9f457f25f122222cfb18ebd2597bdfe`，tree `e1240595f1e36af5e646e36a4972b126269680d1`。共同祖先 `76af48f5eb86568f778efe5555f8e76074f3b978`。两端分叉，main 独有4提交，候选独有17提交；不能直接用普通快进更新 main，更不能强推覆盖。

main 独有变化只有7个文档/流程文件。连接器读取及独立审查已确认：
- `.github/pull_request_template.md`、`CONTRIBUTING.md`、`docs/tasks.md` 与候选逐字一致。
- `README.md`、`docs/README.md`、`docs/evidence/README.md`、`docs/tasks/README.md` 的候选变化是新增 E/I/P 精确验收、ADR0014 导航和 T070 当前状态；main 新增的阅读入口、贡献指南及流程约束已保留。
- 未发现 main 独有产品代码需要丢弃或重写。

原候选 #49 原生验证在 browser_delivery 失败，main 集成未执行。诊断候选 `173d08cfeca93629f0dbfd8b3b3a0d2cbf7677e8`（tree `893d41b1dc8f9a7981d62745146c861d0bb2b94c`）仅新增固定匿名阶段和证据。须等待当前精确候选原生验证成功后，再读 main HEAD 确认没有移动；在新的 `feat/t070-integration` 隔离分支创建保留双方父历史的合并提交，树采用逐文件审查的候选结果，然后验证集成 SHA 的 CI。不是声称 Git 自动无冲突合并。

若 main 已移动，先重新审查新增差异。不得依赖本记录强推、改写历史或跳过测试。新环境部署另行校验，不复用旧能力文件。


## 执行前更新

#53 精确 `0a204d9382386ff801e9dce410c8ef554fa7a7d4` / tree `63a74384d5d4bcb8fd3c89c4cbfcdc08f510753c` 已全部通过。再次读取 main 仍为 ae3e83f；后续变化仅诊断、两选择器标签修正与对应测试/证据。可以创建保留 main 与该候选两个父提交的隔离分支；不得将未来文档提交或集成提交冒充 #53 原生执行版本。
