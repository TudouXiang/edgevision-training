"""Synthetic strict package contract tests; no model execution."""
from copy import deepcopy
from uuid import uuid4
import pytest


def test_package_source_and_frozen_contract_exist():
    from app import package_contract
    assert hasattr(package_contract, 'FrozenPackage')
    assert hasattr(package_contract, 'PackageEvidence')


def test_package_template_identity_rejects_extra_and_nonliteral_types():
    from app.package_contract import TemplateIdentity
    value = {'protocol': 'edgevision-python-onnx-v1', 'image_protocol': 'detection-image-v1',
             'target': 'linux-x86_64-cpython312-cpu', 'template_sha256': 'a'*64,
             'core_sha256': 'b'*64, 'lock_sha256': 'c'*64}
    assert TemplateIdentity.model_validate(value).model_dump() == value
    for bad in ({**value, 'extra': 'private'}, {**value, 'core_sha256': True}, {**value, 'target': 'cuda'}):
        with pytest.raises(ValueError): TemplateIdentity.model_validate(bad)


def test_package_evidence_requires_exact_bundle_and_positive_strict_sizes():
    from app.package_contract import PackageEvidence
    value = {'schema_version': 1, 'job_id': str(uuid4()), 'run_id': str(uuid4()), 'input_sha256': 'a'*64,
             'outputs': [{'path': name, 'size_bytes': 42, 'sha256': 'b'*64} for name in ('package.zip', 'metadata.json', 'validation.json')]}
    assert len(PackageEvidence.model_validate(value).outputs) == 3
    for mutation in ('bool', 'missing', 'duplicate', 'extra', 'path'):
        bad=deepcopy(value)
        if mutation=='bool': bad['outputs'][0]['size_bytes']=True
        if mutation=='missing': bad['outputs'].pop()
        if mutation=='duplicate': bad['outputs'][1]=deepcopy(bad['outputs'][0])
        if mutation=='extra': bad['outputs'][0]['server_path']='secret'
        if mutation=='path': bad['outputs'][0]['path']='../package.zip'
        with pytest.raises(ValueError): PackageEvidence.model_validate(bad)


def test_frozen_package_rejects_wrong_project_and_model(inference_ready):
    from app.package_contract import FrozenPackage
    from app.inference_inputs import model_snapshot
    from app.database import transaction
    context, _, onnx, _ = inference_ready
    with transaction() as connection:
        model = model_snapshot(connection, context[1], onnx['id'], 'onnx')
    value = {'schema_version': 1, 'project_id': context[1], 'model': model,
             'params': {'onnx_artifact_id': onnx['id']}, 'template': {'protocol': 'edgevision-python-onnx-v1',
             'image_protocol': 'detection-image-v1', 'target': 'linux-x86_64-cpython312-cpu',
             'template_sha256': 'a'*64, 'core_sha256': 'b'*64, 'lock_sha256': 'c'*64},
             'runtime_binding': 'd'*64, 'code_version': 'e'*64, 'template_validation_sha256': 'f'*64}
    assert str(FrozenPackage.model_validate(value).project_id) == context[1]
    for field in ('project_id', 'model_id', 'schema_version'):
        bad=deepcopy(value)
        if field=='model_id': bad['params']['onnx_artifact_id']=str(uuid4())
        elif field=='schema_version': bad[field]=True
        else: bad[field]=str(uuid4())
        with pytest.raises(ValueError): FrozenPackage.model_validate(bad)

# Reuse explicit synthetic lineage fixtures only.
from test_inference import inference_ready
from test_export import export_ready
from test_training import ready
from test_dataset_api import data_root
