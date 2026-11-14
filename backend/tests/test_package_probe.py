"""Parent probe boundary tests; mocks never constitute native acceptance."""
import pytest
from test_inference import inference_ready
from test_export import export_ready
from test_training import ready
from test_dataset_api import data_root


def test_parent_rejects_incomplete_receipt():
    from app.package_probe import completed_receipt
    good={'reason':'completed','exit_code':0,'logs_complete':True,'started':True}
    assert completed_receipt(good)==good
    for key,value in [('reason','timeout'),('exit_code',1),('logs_complete',False),('started',False)]:
        with pytest.raises(ValueError):completed_receipt({**good,key:value})
    with pytest.raises(ValueError):completed_receipt(None)


def test_unavailable_reference_prevents_standalone_execution(monkeypatch,tmp_path):
    from app import package_probe as probe
    monkeypatch.setattr(probe,'data_root',lambda:tmp_path)
    monkeypatch.setattr(probe,'reference_capability',lambda:{'available':False})
    with pytest.raises(ValueError,match='reference'):probe.run_probe('not-used')


def test_expansion_is_exact_and_preserves_existing_destination(inference_ready,tmp_path):
    from app.package_probe import expand_candidate
    from app.package_bundle import build_bundle
    from app.package_cli import verify_package
    from test_package_bundle import candidate
    value=candidate(inference_ready);source=tmp_path/'source';source.mkdir()
    info=build_bundle(value,source);target=tmp_path/'target';target.mkdir()
    assert expand_candidate(source/'package.zip',value,target)==info
    assert verify_package(target/'package')==info['manifest']
    with pytest.raises(FileExistsError):expand_candidate(source/'package.zip',value,target)


def test_probe_phase_accepts_only_closed_anonymous_labels(monkeypatch,tmp_path):
    from app import package_probe as probe
    monkeypatch.setattr(probe,'data_root',lambda:tmp_path)
    probe.phase('raw')
    from app.run_files import read_json
    assert read_json(tmp_path/'package-probe-phase.json')=={'phase':'raw'}
    with pytest.raises(ValueError):probe.phase('secret /home/person/model')
