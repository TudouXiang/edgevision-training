# T060 I 图片推理整合记录（2026-11-05 UTC）

## 范围与结论

I业务仍为review_required；源码已完成限定独立审查，不是业务accepted。E 保留原限定验收；P 仍501，T060整体及T070未验收。
本记录只包含轻量、合成文件/图像、普通受管进程及前端 mock 测试，没有真实模型/ORT/probe/浏览器执行。
未经当前精确源码的单独授权与安全审查，不运行原生验证入口。

## 第一轮完整整合

- 后端候选：`af2b7dfbc49e98aa9d3f8cf64a589a6e81cd25b9`。
- 前端候选：`36fc00e885be002ccaa72ec6b60806a9f01e2df4`。
- 无冲突整合：`8bdf0442396fb0aa76d77d90c05f68585a790f09`。
- 文件树：`c10bee68b07f13ca1d6172b2a100961ccaab7824`。
- 命令：`EDGEVISION_ONNX_POLICY_ROOT= EDGEVISION_ML_POLICY_ROOT= EDGEVISION_SMOKE_ASSET= EDGEVISION_INFERENCE_POLICY_ROOT= python3 scripts/dev.py check`。
- 退出码0。后端591 passed、9 native opt-in skipped；前端100 passed（7文件）；vue-tsc/Vite构建、OpenAPI/TS生成漂移检查通过。后端耗时350.39秒，不是模型性能数据。
- `git diff 0d40ffe..HEAD --check` 退出0。
- 完整Git备份校验通过；临时全新bare clone的`git fsck --full`退出0，恢复上述精确提交和树。I补丁在临时index从0d40ffe还原同一树。没有备份凭据、模型或用户图片。

## 审查发现与待闭环项

已由先前独立复核关闭：PNG16解码降位漏洞、I文件成员严格整数/容量约束、PT/ONNX父来源与摘要交叉绑定。
第一轮整合后，独立审查另发现：下载完整性检查后的文件竞态应规范返回409；runner输入变化/运行环境/存储异常需稳定分类；显式retry丢响应后编辑表单会丢source身份；恢复记录需按用户和项目共同分区，避免账号切换生成新任务。这些均须修复、负向回归并独立复核后才能关闭。

前端失响应恢复按钮的后续增量不在本轮100项范围内。真实HTTP/原生负向/图片比较和独立I浏览器验证入口也不在上述已执行范围。
当前未执行：I真实PT与ONNX图片结果比较、真实I HTTP与浏览器、Windows I原生/新增I进程远端矩阵、独立部署包、CUDA/NPU、正式精度和性能实验。

后续记录按精确新提交追加，不把本轮通过计数覆盖到新改动，也不将旧76af原生E证据算作I证据。

## 第二轮冻结整合与最终源码审查

2026-11-05，冻结整合 `069ac5efd50a1907bd29b48efae4d94ac4b8be78`：

- `python3 scripts/dev.py check` 退出0。后端646 passed、14 native opt-in skipped（342.52秒），前端117 passed / 7文件；vue-tsc/Vite与OpenAPI/TS漂移检查通过。脚本主动从普通check子环境移除9项原生开关，未执行模型或浏览器。14项跳过=训练3+E6+I5。
- 之前冻结450b50fa41a3087b7548e68ed486f8fa84b3f153运行`cd backend && .venv/bin/python tests/http_restart_probe.py`退出0：`http_api_restart=passed independent_worker=passed tree_exit=passed`。这是既有普通HTTP/进程探针，不是I原生推理。
- 1dbb08bf0ab739214d1817b03f687c9142c30e0a的隔离入口/文档聚焦回归204 passed、5 native skipped、34 subtests，退出0。

独立审查分别绑定：

1. 后端d4e5f855a850494dfbf502fcba8f77ed9bd57f98：限定源码accept。155项及8子测试通过；契约、差异及强制阻断ML导入检查通过。6类发现均已闭合，包括PNG16、严格成员、来源绑定、下载竞态、执行错误协议、损坏I元数据的规范化409。
2. 前端db3801774c028de52381ede5481ac2a41f4c1b32：限定源码accept。117候选测试+5项独立回归=122通过，build/typecheck:e2e通过。显式retry身份丢失和跨账号恢复两个缺陷已分别复现并验证修复。
3. 验证入口1dbb08b：限定源码accept。198项通过、5原生跳过、34子测试；联网准备专项30项通过。默认浏览器discovery5、I专用discovery1，均executed=0/NOT_RUN。Dockerfile、联网安装流程、固定资产获取与联合依赖锁相对真实E基线76af未变。

v3当前执行必须有全部十阶段，历史v2七阶段只可历史解析，不能冒充新I通过。网络隔离、非root、无宿主挂载及资源限制保持；ML共享450秒、外层执行480秒、job20分钟未放宽。普通workflow显式清空旧2+新3项原生开关，普通check子环境清空全部9项，普通浏览器不发现I测试。

边界：standalone `inference_http_probe.py` 的exclusive日志打开异常可能在直接运行时显示路径；正式隔离入口已私有捕获全部子输出且强制fresh root，因此不是当前隔离链阻塞项。不要把直接运行这个helper当作同等匿名接口。匿名公开输出仅闭集阶段摘要。

随后只整合已公开的7份仓库导航文档（原docs分支3c259bd，与main已合并导航一致），更新E/I状态摘要并追加证据；不改main、不把源码审查等同原生执行。最终候选与069ac5e的运行源码、生成契约和工作流必须逐文件核对无差异。

**剩余：明确发布授权、最终公开SHA的普通CI、该精确SHA一次隔离I执行授权及实际结果。真实I仍全部NOT_RUN，P未放行。**
