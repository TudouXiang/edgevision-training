# T060 重建依赖计划（2026-11-04 UTC）

状态：官方发布元数据重新核对、安装计划/静态测试通过。**没有下载wheel、安装或导入ML，没有实际模型执行。** 不沿用丢失环境的运行结果。

`requirements-delivery-linux-cpu.lock` 保留公开T050的全部62条固定版本/摘要，追加5条，共67条；原训练锁文件未修改。目标仅Linux x86_64、Python3.12，其他平台未验证。

本轮通过官方PyPI JSON API逐项读取元数据，确认下面的既定wheel摘要存在且未被撤回：

- ONNX 1.23.2：cp312 abi3、manylinux2.27/2.28 x86_64，Apache-2.0项目。其最低依赖NumPy1.23.2、protobuf6.31.1、typing_extensions4.7.1、ml_dtypes0.5.4均由联合锁覆盖。[发布元数据](https://pypi.org/pypi/onnx/1.23.2/json)
- ONNX Runtime 1.31.1：cp312、manylinux2.28 x86_64；需要flatbuffers、NumPy、packaging、protobuf，均已固定。[发布元数据](https://pypi.org/pypi/onnxruntime/1.31.1/json)
- protobuf 7.36.2：cp310 abi3、manylinux2014 x86_64。[发布元数据](https://pypi.org/pypi/protobuf/7.36.2/json)
- ml_dtypes 0.6.0：cp312、manylinux2.27/2.28 x86_64；Python3.12分支需要NumPy2.0或更新，原锁满足。[发布元数据](https://pypi.org/pypi/ml_dtypes/0.6.0/json)
- flatbuffers 25.12.19：通用Python wheel。[发布元数据](https://pypi.org/pypi/flatbuffers/25.12.19/json)

完整官方文件SHA256保存在依赖锁中。这些是公开依赖指纹，不是图片、数据集或私有模型产物指纹。元数据约束匹配不证明安装、ABI、算子兼容、数值一致性或安全隔离已经通过。

`python scripts/install_ml.py --delivery --check` 仅检查目标平台和计划，不创建环境、安装包、导入ML或执行模型。实际安装使用独立 `.venv-delivery` 和仅wheel/require-hashes；不更改轻量 `.venv` 或原训练 `.venv-ml`。导入安装器模块也没有安装副作用。实际安装与探针仍需受审查的执行边界，当前未运行。

新单元测试3项通过，覆盖原62条完全保留、独立环境/锁选择、只读检查不执行安装操作。源代码和依赖计划存在不代表ONNX能力可用。
