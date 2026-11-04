# 项目许可核验记录 · 2026-11-04 UTC

基线：`feat/t040-worker-validation` / `3795759`；开始时 `git status --short` 为空。
本次范围仅许可文档，既有源码、依赖、模型、数据与参考包不改动。

## LICENSE 来源与完整性

通过官方 GitHub 连接器读取 SPDX 官方仓库
[`spdx/license-list-data/text/AGPL-3.0-only.txt`](https://github.com/spdx/license-list-data/blob/main/text/AGPL-3.0-only.txt)，
以工具返回的 base64 原始字节写入 `LICENSE`，未手工改写、补写或删除条文。

- 长度：34,020 字节。
- SHA-256：`d8a6cc31abc16b6748c7a21f21611f5a1ec33f67d22ca23d7da1c19b95496bee`。
- Git blob SHA-1：`0c97efd25b5974b974ed9a8a18207bc4f55bb338`。
- 本地重新计算 Git blob 身份，与官方工具返回的 `sha` 精确一致。
- 已检查标题、版本/日期、0–17 节、结束标记和完整应用说明。`LICENSE` 的示例包含
  or-later 字样，项目实际选择由 `LICENSE_SCOPE.md` 明确为 only，未修改标准条文。
- GNU 网站本次读取超时；没有把超时写成成功。SPDX 的标识说明页与官方文本均已取得。

Ultralytics 官方 `LICENSE` 同时已读取，Git blob 为
`be3f7b28e564e7dd05eaf59d64adba1a4065ac0e`，标题为 GNU AGPL v3。
官方许可页、PyTorch/ONNX/ONNX Runtime 官方 LICENSE 也已只读核对；未选择其未来版本，
这些网页核对不替代未来精确发行包和资产的审计。

## 只读盘点

使用 Python 标准库读取 JSON/TOML/发行包文本、ZIP 目录及指定 README/package.json，
没有安装新依赖、解压执行、导入参考代码或运行其脚本。

| 输入 | SHA-256 / 结果 |
| --- | --- |
| `backend/uv.lock` | `eded065529c5fbe8a3b9fd809bf082eabeddb62645820d23af6c48af88406593` |
| `web/package-lock.json` | `bee71004ba6918f83f2e9920af8f486962bb064287505c5610822ef0cceadeee` |
| `reference/edgevision-studio-frontend.zip` | `c6f5bb8f8fc561e52caf69f32439c2d0505801f2f85d33191657987d4a964f41` |
| Python 锁文件 | 33 个第三方包，另含项目自身记录；当前 Linux 安装 32 个，版本全部匹配；colorama 0.4.6 为未安装的 Windows 条件包 |
| Web 锁文件 | 208 个第三方包路径，均有许可字段；直接依赖的本地包及许可文件已核对 |
| 参考 ZIP | 69 条目，总未压缩大小 565,386 字节；4 个 SVG；无 LICENSE/LICENCE/COPYING/NOTICE/COPYRIGHT 命名文件；根 package.json 无 license 字段 |
| 已跟踪 ML/图片资产 | 除参考 ZIP 外，未发现 `.pt`、`.onnx`、`.png`、`.jpg` 等已跟踪模型/图片文件；未据此判断未来资产权利 |

Python 已安装包的许可元数据分布：MIT 17、BSD-3-Clause 8、Apache-2.0 1、MIT-CMU 1、
MIT-0 1、BSD-2-Clause 1、MPL-2.0 1、Apache-2.0 OR BSD-2-Clause 1、PSF-2.0 1。
Web 分布与全部直接依赖见根 `THIRD_PARTY_NOTICES.md`。额外检查了 Lucide 的
Feather/MIT 声明、Playwright 的 Puppeteer NOTICE、Pillow 的 70,307 字节多组件 LICENSE
与 certifi 的 Mozilla CA 说明。包级 SPDX 字段不是完整嵌入组件或权利链审计。

## 检查与未执行项

- 读取 `git status --short`、`git log -1 --oneline`、`git ls-files` 及相关文档：退出 0。
- Python ZIP/JSON/TOML/METADATA 盘点和许可身份断言：退出 0。
- 最终 LICENSE 哈希、0–17 节、文档相对链接、锁文件/参考 ZIP 不变及文档范围检查：退出 0。
- `git diff --check`：退出 0。
- 应用测试、构建、ML 安装/训练、模型下载、公开部署、二进制分发审计：**未执行**。
- 无提交或推送；本次不会改变 T050 的 blocked 状态，也不宣称所有许可风险已消除。
