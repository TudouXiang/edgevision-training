# T040：Worker与异步数据校验

执行者：实现Agent。前置：T030 accepted，进程方案明确；状态blocked。

目标：真正的单实例Worker、FIFO/单槽、原子领取、受管子进程、幂等、日志游标、取消和恢复核对，接入dataset_check。复用唯一状态转换入口。

不做：训练算法、Celery/Redis、远程Worker、并行任务、自动重试/续训。测试使用明确受限的本地子进程夹具，Fake绝不被生产配置选中。

必须验证：并发提交/领取只运行一个；重复幂等键；排队取消；运行取消；子孙进程退出；取消与完成竞争；退出码0但缺产物；API重启；强制终止Worker后的遗留核对；未知/复用PID不误杀；已发布文件与未提交DB记录的崩溃恢复。恢复不能确认安全时应阻塞新领取。

Linux 和 Windows 均需分别实测。Windows T010 只支持无子孙进程的占位 `task_process`，其 `windows-unverified` 不是可用于恢复的主机 boot ID；接入真实适配器前须补齐进程树终止、重启后的身份核验及竞争故障注入（ADR 0006）。未取得 Windows 环境时对应验收标 NOT_RUN，不据 Linux 结果放行 Windows 能力。

以真实进程测试而非只mock函数调用验收A08-A10/A12。完成数据集上传→排队→校验→ready/invalid与日志的浏览器链路。输出docs/evidence/T040-report.md及实际进程方案记录。
