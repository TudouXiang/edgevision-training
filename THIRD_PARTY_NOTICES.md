# 第三方组件与资产说明

本项目的 AGPL-3.0-only 选择不重授权第三方组件。下表是 **2026-11-04** 对当前锁文件、
本地已安装发行包元数据与许可文件的盘点，不是完整二进制发行包的 NOTICE 合集或法律兼容性认证。
实际发行时必须按精确版本收集并保留所包含组件的完整 LICENSE、NOTICE、版权与源码义务，
不能用此摘要替代它们。审计范围和指纹见 [核验记录](docs/evidence/licensing-2026-11-04.md)。

## 当前 Python 直接依赖

精确版本来自 `backend/uv.lock`；许可来自该版本本地 `.dist-info/METADATA` 与随包许可文件。
链接指向发行包声明的官方源码仓库，未来版本变更必须重新核对。

| 组件 | 锁定版本 | 包级许可 | 官方源码 |
| --- | --- | --- | --- |
| argon2-cffi | 25.1.0 | MIT | [hynek/argon2-cffi](https://github.com/hynek/argon2-cffi) |
| FastAPI | 0.141.1 | MIT | [fastapi/fastapi](https://github.com/fastapi/fastapi) |
| Pydantic | 2.13.5 | MIT | [pydantic/pydantic](https://github.com/pydantic/pydantic) |
| Pillow | 12.3.0 | MIT-CMU；wheel 内另有第三方条款 | [python-pillow/Pillow](https://github.com/python-pillow/Pillow) |
| python-multipart | 0.0.33 | Apache-2.0 | [Kludex/python-multipart](https://github.com/Kludex/python-multipart) |
| PyYAML | 6.0.3 | MIT | [yaml/pyyaml](https://github.com/yaml/pyyaml) |
| Uvicorn | 0.54.0 | BSD-3-Clause | [Kludex/uvicorn](https://github.com/Kludex/uvicorn) |
| SQLAlchemy | 2.1.1 | MIT | [sqlalchemy/sqlalchemy](https://github.com/sqlalchemy/sqlalchemy) |
| Alembic | 1.20.0 | MIT | [sqlalchemy/alembic](https://github.com/sqlalchemy/alembic) |
| pytest（开发） | 9.1.1 | MIT | [pytest-dev/pytest](https://github.com/pytest-dev/pytest) |
| HTTPX（开发） | 0.28.1 | BSD-3-Clause | [encode/httpx](https://github.com/encode/httpx) |

锁文件含 33 个第三方 Python 包；本 Linux 环境安装了其中 32 个且版本吻合。仅 Windows
条件包 colorama 0.4.6 未安装，官方 [LICENSE](https://github.com/tartley/colorama/blob/master/LICENSE.txt)
是 BSD-3-Clause，但该精确 Windows wheel 的内容尚未核验。

特别保留：certifi 2026.7.22 的 Mozilla CA 数据与 MPL-2.0 说明；packaging 26.3 的
Apache-2.0 / BSD-2-Clause 双许可；typing-extensions 4.16.0 的 PSF-2.0；cffi 2.1.1
的 MIT-0。Pillow wheel 的 LICENSE 共 70,307 字节，包含图像编解码等第三方条款，
不可简化成仅 MIT-CMU。随包原件位于各 `.dist-info/licenses/`（或发行包声明的路径），
本次未编辑这些文件。MPL 分发与源码义务参见 [Mozilla 官方说明](https://www.mozilla.org/en-US/MPL/2.0/FAQ/)。

## 当前 Web 直接依赖

精确版本与包级许可来自 `web/package-lock.json`，并核对直接依赖的本地许可文件。

| 组件 | 锁定版本 | 包级许可 | 官方源码 |
| --- | --- | --- | --- |
| @lucide/vue | 1.47.0 | ISC；Feather 衍生图标另保留 MIT | [lucide-icons/lucide](https://github.com/lucide-icons/lucide) |
| Element Plus | 2.14.6 | MIT | [element-plus/element-plus](https://github.com/element-plus/element-plus) |
| Vue | 3.5.43 | MIT | [vuejs/core](https://github.com/vuejs/core) |
| Vue Router | 4.6.4 | MIT | [vuejs/router](https://github.com/vuejs/router) |
| @playwright/test（开发） | 1.64.1 | Apache-2.0；含 NOTICE | [microsoft/playwright](https://github.com/microsoft/playwright) |
| @vitejs/plugin-vue（开发） | 6.0.9 | MIT | [vitejs/vite-plugin-vue](https://github.com/vitejs/vite-plugin-vue) |
| @vue/test-utils（开发） | 2.5.1 | MIT | [vuejs/test-utils](https://github.com/vuejs/test-utils) |
| happy-dom（开发） | 20.14.6 | MIT | [capricorn86/happy-dom](https://github.com/capricorn86/happy-dom) |
| openapi-typescript（开发） | 7.13.0 | MIT | [openapi-ts/openapi-typescript](https://github.com/openapi-ts/openapi-typescript) |
| TypeScript（开发） | 5.9.3 | Apache-2.0 | [microsoft/TypeScript](https://github.com/microsoft/TypeScript) |
| Vite（开发） | 7.3.6 | MIT | [vitejs/vite](https://github.com/vitejs/vite) |
| Vitest（开发） | 4.1.12 | MIT | [vitest-dev/vitest](https://github.com/vitest-dev/vitest) |
| vue-tsc（开发） | 3.3.11 | MIT | [vuejs/language-tools](https://github.com/vuejs/language-tools) |

锁文件有 208 个第三方包路径，均有包级许可字段：MIT 181、ISC 10、Apache-2.0 6、
BlueOak-1.0.0 6、BSD-3-Clause 2、BSD-2-Clause 1、Python-2.0 1、`MIT OR CC0-1.0` 1。
这是包路径计数，不是独立版权作品数。传递依赖包括 argparse 2.0.1（Python-2.0）、
type-fest 4.41.0（MIT OR CC0-1.0）以及六个 BlueOak 路径。包级字段不能覆盖包内所有
嵌入作品；Lucide 的完整 LICENSE 同时保留 Lucide Icons and Contributors 与 Cole Bemis /
Feather 的声明，Playwright 的 NOTICE 包含 Puppeteer 来源说明，均须随实际分发内容保留。

## T060 重建联合锁的新增边界

当前源码另有 `backend/requirements-ml-linux-cpu.lock` 与
`backend/requirements-delivery-linux-cpu.lock`。后者保留训练锁的全部固定条目，
新增 ONNX 1.23.2、ONNX Runtime 1.31.1、protobuf 7.36.2、ml_dtypes 0.6.0 与
flatbuffers 25.12.19。官方发行元数据与文件摘要的本轮核对见
[依赖重建计划](docs/evidence/T060-rebuild-dependency-plan.md)。这里只发布依赖清单，
不随源码发布其 wheel、原生库、模型权重或镜像；未把元数据核对说成安装/运行或完整许可审计。

本轮没有改变项目 AGPL-3.0-only 选择，亦未覆盖第三方许可。未来二进制/部署包交付前，
必须按实际装入的精确 wheel 和组件收集原始 LICENSE、NOTICE 与适用版权声明，
单独核对输入权重及用户产物的权利。T060 的该发行审计仍待完成；下节保留早期规划记录，
其中“尚未接入”仅描述当时状态，不覆盖上述联合锁。

## 历史 ML 规划记录：当时尚未接入项目锁文件

当前两个锁文件均未引入下列组件。这里记录官方上游的许可方向，不宣称具体版本、wheel、
模型权重或数据集已经获准使用。

| 计划组件 | 当前官方依据 | 接入前仍需完成 |
| --- | --- | --- |
| Ultralytics / YOLO11n | [官方 LICENSE](https://github.com/ultralytics/ultralytics/blob/main/LICENSE)；[官方许可说明](https://www.ultralytics.com/license) | 锁定发行版本、依赖与哈希；采用 AGPL 路线；逐项核验权重、数据与产物条款，不购买 Enterprise 许可 |
| PyTorch | [官方 LICENSE](https://github.com/pytorch/pytorch/blob/main/LICENSE)，BSD 风格许可及版权声明 | 核对精确 CPU/CUDA wheel、所含原生组件及附加许可，不把仓库顶层许可当作完整 wheel 清单 |
| ONNX | [官方 LICENSE](https://github.com/onnx/onnx/blob/main/LICENSE)，Apache-2.0 | T060 锁定版本，保留适用 NOTICE，核验导出模型的独立资产权利 |
| ONNX Runtime | [官方 LICENSE](https://github.com/microsoft/onnxruntime/blob/main/LICENSE)，MIT | T060 核对精确发行包及其第三方通知 |
| RKNN 工具链 | 尚未选定或核验 | 仅保留接口，不安装、不分发、不声称许可或设备验证已完成 |

官方上游页面可能更新，实际接入以所选版本原件为准。Ultralytics 官方许可说明涉及其
代码、模型与训练管线；采用本项目 AGPL 路线不会自动解决未知资产的来源问题。

## 历史参考包和用户资产

`reference/edgevision-studio-frontend.zip` 的 69 个条目包含旧原型、依赖清单与四个 SVG，
未发现许可/版权/NOTICE 文件，`package.json` 也没有项目许可字段。`private: true`
仅是包管理配置，不是授权。其 Next/React/Carbon/vinext 等依赖的许可不能证明原型本身或
SVG 的权利，整个参考包按 [LICENSE_SCOPE.md](LICENSE_SCOPE.md) 排除，不作为生产资产。
用户数据集、图片、标注、权重及训练产物的许可另行记录，不因上传或导出自动变为 AGPL。
