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


@pytest.mark.parametrize('error,expected',[(AssertionError('private'),'assertion'),(ValueError('private'),'contract'),(RuntimeError('private'),'unknown')])
def test_export_step_records_only_closed_class(error,expected):
    m=probe();result={}
    with pytest.raises(type(error)):
        with m.export_step(result,'export_result'):
            raise error
    assert result=={'export_failure':{'phase':'export_result','error':expected}}


def test_export_step_rejects_untrusted_phase_and_does_not_mark_success():
    m=probe();result={}
    with pytest.raises(ValueError):
        with m.export_step(result,'private/path'):pass
    assert result=={}
    with m.export_step(result,'export_probe'):pass
    assert result=={}


def test_export_process_failures_never_expose_command_or_output():
    import subprocess
    m=probe()
    for error,expected in ((subprocess.TimeoutExpired(['secret'],1,output='secret'),'timeout'),(subprocess.CalledProcessError(27,['secret'],output='secret'),'process_failed')):
        result={}
        with pytest.raises(type(error)):
            with m.export_step(result,'export_probe'):raise error
        assert result=={'export_failure':{'phase':'export_probe','error':expected}}


def test_export_task_diagnostic_drops_private_payload():
    m=probe();result={}
    with pytest.raises(AssertionError):
        with m.export_step(result,'export_result'):
            m.require_export_success(result,{'state':'failed','error_code':'ONNX_MODEL_INVALID','error_message':'secret','id':'secret'})
    assert result=={'export_failure':{'phase':'export_result','error':'assertion','task_state':'failed','task_code':'ONNX_MODEL_INVALID'}}
    result={}
    with pytest.raises(AssertionError):
        with m.export_step(result,'export_result'):
            m.require_export_success(result,{'state':'secret','error_code':'secret'})
    assert result['export_failure']['task_state']==result['export_failure']['task_code']=='unknown'


def test_export_sidecar_bounded_closed_and_no_links(tmp_path):
    m=probe();path=tmp_path/'export-failure.json'
    assert m.read_export_detail(path)=='unknown'
    for raw in ('{"schema_version":1,"code":"compare_tolerance"}',):
        path.write_text(raw);assert m.read_export_detail(path)=='compare_tolerance'
    for raw in ('{"schema_version":true,"code":"graph_guard"}','{"schema_version":1,"code":"secret"}','{"schema_version":1,"code":"graph_guard","private":"secret"}','{"schema_version":1,"code":"graph_guard","code":"compare_tolerance"}','x'*1025):
        path.write_text(raw);assert m.read_export_detail(path)=='unknown'
    path.unlink();source=tmp_path/'private';source.write_text('{"schema_version":1,"code":"graph_guard"}')
    path.symlink_to(source);assert m.read_export_detail(path)=='unknown'


def test_export_detail_requires_bound_completed_drain():
    m=probe();row={'id':'job','run_id':'run','kind':'export_onnx','status':'failed','error_code':'ONNX_MODEL_INVALID'}
    receipt={'job_id':'job','run_id':'run','tree_exited':True,'reason':'completed','exit_code':74,'started':True,'logs_complete':True}
    assert m.completed_export_drain(row,receipt)
    for key,bad in (('job_id','other'),('run_id','other'),('tree_exited',False),('started',False),('logs_complete',False),('exit_code',0),('reason','timeout')):
        assert not m.completed_export_drain(row,{**receipt,key:bad})
    for key,bad in (('kind','train'),('status','running'),('error_code','RUNNER_FAILED')):
        assert not m.completed_export_drain({**row,key:bad},receipt)
    assert not m.completed_export_drain(row,None)


def test_verified_export_detail_propagates_only_model_invalid():
    m=probe()
    for code in ('ONNX_MODEL_INVALID','RUNNER_FAILED'):
        result={}
        with pytest.raises(AssertionError):
            with m.export_step(result,'export_result'):
                m.require_export_success(result,{'state':'failed','error_code':code},'graph_guard')
        assert ('detail' in result['export_failure'])==(code=='ONNX_MODEL_INVALID')


def test_export_ancillary_database_failure_keeps_original_failure():
    import sqlite3
    m=probe();task={'state':'failed','error_code':'ONNX_MODEL_INVALID'}
    def broken():raise sqlite3.OperationalError('private database')
    def forbidden(*args,**kwargs):raise AssertionError('must not read sidecar')
    detail=m.export_diagnostic('private-id',task,broken,forbidden,forbidden)
    assert detail=='unknown'
    result={}
    with pytest.raises(AssertionError):
        with m.export_step(result,'export_result'):m.require_export_success(result,task,detail)
    assert result['export_failure']['task_code']=='ONNX_MODEL_INVALID'
    assert result['export_failure']['detail']=='unknown'


def test_export_sidecar_symlink_parent_is_unknown(tmp_path):
    m=probe();directory=tmp_path/'real';directory.mkdir()
    (directory/'export-failure.json').write_text('{"schema_version":1,"code":"graph_guard"}')
    link=tmp_path/'link';link.symlink_to(directory,target_is_directory=True)
    assert m.read_export_detail(link/'export-failure.json')=='unknown'
