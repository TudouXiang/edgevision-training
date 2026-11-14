"""Strict gate tests use synthetic proofs, never runtime acceptance."""
from copy import deepcopy
import pytest
from test_package_probe_contract import record
from app.training_assets import digest_json


def gate(monkeypatch):
    from app import package_assets as assets
    value=record();environment={'synthetic':True};adapter={'synthetic':'fixed'}
    reference={'adapter':{'synthetic':'reference'}}
    identity={'adapter':adapter,'package_template':value['template'],'package_environment':environment,
        'reference_runtime_binding':digest_json(reference),'reference_code_version':digest_json(reference['adapter'])}
    value.update(runtime_binding=digest_json(identity),code_version=digest_json(adapter),environment_sha256=digest_json(environment),
        reference_runtime_binding=identity['reference_runtime_binding'],reference_code_version=identity['reference_code_version'])
    value['reference'].update(runtime_binding=value['reference_runtime_binding'],code_version=value['reference_code_version'])
    for name,proof in [('raw_task','standalone'),('cli_task','cli')]:
        value[name].update(runtime_binding=value['runtime_binding'],code_version=value['code_version'])
        value[proof].update(task_sha256=digest_json(value[name]),environment_sha256=value['environment_sha256'])
    monkeypatch.setattr(assets,'runtime_identity',lambda:deepcopy(identity))
    monkeypatch.setattr(assets,'read_json',lambda *a:deepcopy(value))
    monkeypatch.setattr(assets,'source_hashes',lambda:{'cli_sha256':'c'*64,'bootstrap_sha256':'d'*64})
    return assets,value,identity


def test_gate_accepts_only_current_strict_proof(monkeypatch):
    assets,value,_=gate(monkeypatch)
    assert assets.validated_template()=={'template':value['template'],'record_sha256':digest_json(value)}
    assert assets.capability()['available'] is True


@pytest.mark.parametrize('fault',['runtime','template','environment','entry','reference','missing_receipt'])
def test_gate_rejects_stale_or_incomplete_proof(monkeypatch,fault):
    assets,value,identity=gate(monkeypatch)
    if fault=='runtime':identity['adapter']['synthetic']='changed'
    elif fault=='template':identity['package_template']['core_sha256']='0'*64
    elif fault=='environment':identity['package_environment']['synthetic']=False
    elif fault=='entry':value['cli_task']['bootstrap_sha256']='0'*64
    elif fault=='reference':value['reference_runtime_binding']='0'*64
    else:value['standalone']['receipt_sha256']=None
    assert assets.capability()['available'] is False


def test_i_success_or_arbitrary_record_cannot_enable_package(tmp_path,monkeypatch):
    from app import package_assets,inference_assets
    monkeypatch.setattr(inference_assets,'capability',lambda:{'available':True})
    monkeypatch.setattr(package_assets,'runtime_identity',lambda:{})
    (tmp_path/'package-capability.json').write_text('{"available":true}')
    monkeypatch.setattr(package_assets,'data_root',lambda:tmp_path)
    assert package_assets.capability()['available'] is False
    assert package_assets.capability()['reason_code']=='PACKAGE_SETUP_REQUIRED'
    with pytest.raises(ValueError):package_assets.validated_template()


@pytest.mark.parametrize('proof', [None, {'schema_version': 1, 'available': False}, {'available': True}])
def test_unproven_capability_does_not_hash_runtime(tmp_path, monkeypatch, proof):
    import json
    from app import package_assets
    monkeypatch.setattr(package_assets, 'data_root', lambda: tmp_path)
    if proof is not None:
        (tmp_path/'package-capability.json').write_text(json.dumps(proof))
    def forbidden():
        pytest.fail('unproven capability performed expensive runtime validation')
    monkeypatch.setattr(package_assets, 'runtime_identity', forbidden)
    assert package_assets.capability()['available'] is False
