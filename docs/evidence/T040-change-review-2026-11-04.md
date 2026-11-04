# T040 独立源码审查与发布候选

2026-11-04 UTC。基线 `efa3284b3462932e34e99701c4099b2887a928ee`，最终源码指纹 `7765a67aa988e39a018133e87b600e43f5459f13c6b75b23ee90f73dd711c8ff`。67 个文件逐项 SHA 与聚合指纹独立复核一致。

## 审查结果

独立只读审查检查了 Linux pidfd/单一 reaper、Windows typed Job Object/初始成员关系/句柄继承、GO 与取消事务、未知遗留进程安全阻塞、完整退出证据、不可变产物与数据库提交、日志边界和前端迟到响应。审查提出的三个问题均已修正并再次读取核对：

1. 浏览器测试收尾逐个尝试停止所有自有服务；任一退出未确认时保留临时根并明确失败，不能覆盖实际 browser 状态。
2. `/proc/<pid>/stat` 按 bytes 解析，避免无关进程的非 ASCII 名称破坏取消。权限拒绝仍失败关闭。
3. Windows guardian 强杀场景在清理前明确断言根/子/孙退出，验证 KILL_ON_JOB_CLOSE，而不是由清理替代证据。

另核对最终 BrokenPipe 竞争修正：控制管道关闭仅延后至原有 drain receipt 核验，不放宽退出证据。诊断名与实际代码一致。新增迁移为 0003，历史 0001/0002 未修改。

## 最终候选独立运行

- `python scripts/dev.py check`：退出 0；unittest 6+11，pytest **91 passed**（45.79 秒，无跳过），Vitest **10 passed**，类型/生产构建和契约漂移检查通过。原始日志 `T040-independent-check-2026-11-04.txt`，SHA-256 `6ad82e943c6b9851a97be9dcd38100c763e95f52edceef02c606c7182497b33f`。这些 unittest 也包含在 pytest 集合内，不合计为不同的测试。
- `cd backend && .venv/bin/python tests/http_restart_probe.py`：退出 0，真实 Uvicorn 换进程、独立 Worker 延续和树退出均 passed。日志 `T040-independent-http-2026-11-04.txt`。
- `git diff --check`：退出 0。发布文件仅项目源码、测试、配置、文档和合成测试证据，无运行数据库、Cookie、凭据或模型权重。

## 待远端证据

源码可作为审查候选发布，不等于 T040 accepted。Windows 原生进程矩阵与四项真实 Chromium 仍 NOT_RUN，须以对应提交的 GitHub Actions 实际结果补证。完整主机重启/掉电、实际 TLS、人工视觉、用户旧库和 ML/硬件未执行。T050 仍 blocked，未修改 main，未合并。
