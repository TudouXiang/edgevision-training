"""Purely synthetic source-lineage fixtures, never a native package receipt."""
from copy import deepcopy
from uuid import uuid4
import pytest
from app.database import transaction
from test_inference import inference_ready
from test_export import export_ready
from test_training import ready
from test_dataset_api import data_root


def frozen(context):
    from app.package_inputs import freeze_source
    base, _, onnx, _ = context
    with transaction() as c: model=freeze_source(c, base[1], onnx['id'])
    return {'schema_version': 1, 'project_id': base[1], 'model': model,
            'params': {'onnx_artifact_id': onnx['id']}, 'template': {'protocol': 'edgevision-python-onnx-v1',
            'image_protocol': 'detection-image-v1', 'target': 'linux-x86_64-cpython312-cpu',
            'template_sha256': 'a'*64, 'core_sha256': 'b'*64, 'lock_sha256': 'c'*64},
            'runtime_binding': 'd'*64, 'code_version': 'e'*64, 'template_validation_sha256': 'f'*64}


def test_freeze_rejects_wrong_project_or_pt(inference_ready):
    from app.package_inputs import freeze_source
    base, pt, onnx, _=inference_ready
    with transaction() as c:
        assert freeze_source(c,base[1],onnx['id'])['source_artifact_id']==onnx['id']
        for project,model in ((str(uuid4()),onnx['id']),(base[1],pt['id'])):
            with pytest.raises(ValueError): freeze_source(c,project,model)


@pytest.mark.parametrize('fault',['source_bytes','source_row','parent_row','snapshot'])
def test_verify_rejects_changed_lineage(inference_ready,fault):
    from app.package_inputs import verify_input
    from app.dataset_storage import resolve_storage_file
    value=frozen(inference_ready)
    assert verify_input(value)==value
    if fault=='source_bytes': resolve_storage_file(value['model']['source_key']).write_bytes(b'changed')
    elif fault=='snapshot': value['model']['source_sha256']='0'*64
    else:
        identifier=value['model']['source_artifact_id'] if fault=='source_row' else value['model']['export_input']['source_artifact_id']
        with transaction() as c: c.execute("UPDATE artifacts SET sha256=? WHERE id=?",('0'*64,identifier));c.commit()
    with pytest.raises((ValueError,OSError)): verify_input(value)


def test_bound_copy_is_private_and_unchanged(inference_ready,tmp_path):
    from app.package_inputs import copy_input, source_binding
    from app.run_files import fingerprint
    value=frozen(inference_ready)
    with transaction() as c: binding=source_binding(c,value)
    path=copy_input(value,tmp_path)
    assert path==tmp_path/'model.onnx'
    assert fingerprint(path)==(value['model']['source_size_bytes'],value['model']['source_sha256'])
    with transaction() as c: assert source_binding(c,value)==binding
    with pytest.raises(FileExistsError): copy_input(value,tmp_path)
