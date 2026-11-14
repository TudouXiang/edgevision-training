import importlib.util
from pathlib import Path
import pytest

@pytest.mark.parametrize('relative',['scripts/real_cpu_measure.py','backend/tests/real_cpu_probe.py'])
def test_native_experiment_refuses_noncontainer_checkout(relative):
    root=Path(__file__).resolve().parents[2];path=root/relative
    assert path.is_file(),'native real experiment helper absent'
    spec=importlib.util.spec_from_file_location('guarded_native',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with pytest.raises(ValueError):module.guard()


def probe():
    path=Path(__file__).resolve().parent/'real_cpu_probe.py'
    spec=importlib.util.spec_from_file_location('probe',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_input_artifacts_remain_non_downloadable():
    m=probe()
    assert hasattr(m,'verify_download'),'restore policy check missing'
    class Response:
        status_code=409
        content=b''
        def json(self):return {'detail':{'code':'ARTIFACT_UNAVAILABLE'}}
    m.verify_download({'kind':'inference_input'},Response())
    Response.status_code=200
    with pytest.raises(ValueError):m.verify_download({'kind':'inference_input'},Response())


def test_interruption_requires_a_real_bound_metric(tmp_path):
    m=probe();assert hasattr(m,'started_metric'),'native metric readiness missing'
    path=tmp_path/'metrics.jsonl';path.write_bytes(b'')
    assert m.started_metric(path,'job','run') is False
    import json
    event={'schema_version':1,'job_id':'job','run_id':'run','seq':1,'epoch':1,'name':'train/box_loss','value':1.0}
    path.write_text(json.dumps(event)+'\n');assert m.started_metric(path,'job','run')
    assert not m.started_metric(path,'other','run')


def test_cleanup_never_promotes_interrupted_or_unsettled_run(monkeypatch):
    m=probe();assert hasattr(m,'cleanup_owned'),'cleanup evidence gate missing'
    monkeypatch.setattr(m,'stop',lambda _:None)
    assert m.cleanup_owned(False,[None],lambda:pytest.fail('verify incomplete'))=='unverified'
    assert m.cleanup_owned(True,[None],lambda:False)=='failed'
    assert m.cleanup_owned(True,[None],lambda:True)=='passed'
    def denied(_):raise RuntimeError('stop failed')
    monkeypatch.setattr(m,'stop',denied)
    assert m.cleanup_owned(True,[None],lambda:True)=='failed'
