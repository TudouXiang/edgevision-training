# License scope / 许可范围

## Project grant

Except for the exclusions below, the original EdgeVision project source code,
scripts, tests, configuration, project-owned generated contracts, and
documentation in this repository are licensed under the **GNU Affero General
Public License, version 3 only (SPDX: AGPL-3.0-only)**, to the extent the respective
copyright holders have authority to grant that license. The complete terms are
in [LICENSE](LICENSE). Copyright remains with the respective rights holders;
this statement does not assert ownership of third-party material.

This program is distributed without any warranty, including the implied
warranties of merchantability or fitness for a particular purpose. See LICENSE
for the full warranty and liability provisions.

本项目选择 **AGPL-3.0-only**，不是 AGPL-3.0-or-later。`LICENSE` 末尾保留的
“How to Apply” 示例是许可证原文的一部分，不改变本项目明确选择的版本。

## Exclusions / 不包含在本项目统一授权中的内容

- **Third-party software and notices:** dependencies, their bundled native
  libraries, generated third-party code, icons, fonts, images and other imported
  material retain their own licenses, copyright notices and attribution duties.
  See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Neither a lockfile entry nor
  a copy in an installation/build directory transfers ownership or replaces
  those terms with the project license. Project build output may contain both
  project and third-party material.
- **`reference/edgevision-studio-frontend.zip` and its contents:** the legacy
  prototype is excluded from this grant. Its project/asset licensing and complete
  provenance have not been verified. No archive-level LICENSE/COPYING/NOTICE was
  found in the read-only audit. Retaining the archive is not permission to reuse
  or redistribute its contents. Keep it out of production and release bundles
  until the relevant rights are established; preserve the original archive and
  any existing notices. Exclusion is not a retroactive clearance for past copies.
- **Datasets, images, annotations, model weights and model outputs:** no license
  to these is granted merely by this repository's LICENSE. Record the source,
  exact version/hash, rights holder or applicable terms and permitted uses for
  each asset. User uploads are not automatically relicensed. Do not assume that
  a framework's code license determines every input or output asset's rights.
- **Names and marks:** no separate trademark or endorsement permission is
  granted by this project notice.

## Distribution, network use and future changes

发布源码、二进制或含第三方组件的部署包时，分别满足 AGPL 与实际组件的条款，保留适用
版权、许可和 NOTICE，并按要求提供完整对应源码。AGPL 第 13 节要求符合该节情形的
修改版本，向远程网络交互用户显著提供免费取得对应源码的方式。发布前须验证源码入口
与所运行版本一致，不能只放一个无法取得对应源码的链接。本次只建立许可文件，尚未
实现或验收运行界面的源码入口，也没有宣布生产发布的许可审计完成。

之后可以在有权决定的范围内调整自有代码的未来许可，但不能仅通过改动 LICENSE，
单方面撤销接收者已经取得的 AGPL 副本权限；这些权限仍受 AGPL 条件约束（见第 2、8、10 节）。
第三方条款、已有贡献者权利和既有授权不会随项目文件改名而消失。

决策、理由及剩余闸门见 [ADR 0010](docs/adr/0010-project-licensing.md)。本范围说明不增加
AGPL 对适用项目代码的限制，也不替代各第三方许可证正文。
