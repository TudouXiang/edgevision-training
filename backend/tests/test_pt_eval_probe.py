"""PT-only lifecycle pure guards; no native model or app process execution."""
import importlib.util,json
from pathlib import Path
import pytest


def load():
    p=Path(__file__).with_name('pt_eval_probe.py');assert p.is_file(),'PT-only probe missing'
    spec=importlib.util.spec_from_file_location('pt_probe_test',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_guard_rejects_host_before_loading_runtime(tmp_path,monkeypatch):
    m=load();monkeypatch.setattr(m,'ROOT',tmp_path)
    monkeypatch.setattr(m,'load',lambda *a:pytest.fail('loaded before root guard'))
    with pytest.raises(ValueError):m.guard()


def test_budget_prevents_late_launch():
    m=load()
    assert m.remaining(200,100,clock=lambda:50)==100
    with pytest.raises(TimeoutError):m.remaining(40,100,clock=lambda:50)


@pytest.mark.parametrize('fault',['job','run','exit','logs','tree','started'])
def test_training_receipt_is_bound_and_complete(fault):
    m=load();row={'id':'job','run_id':'run','kind':'train','status':'succeeded'}
    r={'job_id':'job','run_id':'run','exit_code':0,'logs_complete':True,'tree_exited':True,'started':True,'reason':'completed'}
    assert m.training_settled(row,r)
    if fault=='job':r['job_id']='other'
    if fault=='run':r['run_id']='other'
    if fault=='exit':r['exit_code']=True
    if fault=='logs':r['logs_complete']=False
    if fault=='tree':r['tree_exited']=False
    if fault=='started':r['started']=False
    assert not m.training_settled(row,r)


def test_private_measurement_requires_complete_lineage_and_twenty_predictions():
    m=load();truth=[{'class_id':0,'xyxy':[0,0,1,1]} for _ in range(20)]
    value={'detections':[[] for _ in range(20)],'series':{k:[1.]*20 for k in ('preprocess','model','postprocess','total')},'model_load_ms':1.,'lineage_verified':True}
    metrics=m.measurement_metrics(value,truth)
    assert metrics['tp']==metrics['fp']==0 and metrics['fn']==20
    for bad in ({**value,'lineage_verified':False},{**value,'detections':[]},{**value,'private':'secret'}):
        with pytest.raises(ValueError):m.measurement_metrics(bad,truth)


def test_work_budget_reserves_cleanup_and_http_cannot_launch_after_deadline():
    m=load();assert getattr(m,'WORK_BUDGET',None)==1140
    calls=[]
    class Client:
        def request(self,*args,**kwargs):calls.append((args,kwargs));return 'response'
    assert m.http_request(Client(),100,'GET','/test',clock=lambda:95)=='response'
    assert calls[0][1]['timeout']==5
    with pytest.raises(TimeoutError):m.http_request(Client(),100,'GET','/test',clock=lambda:101)
    assert len(calls)==1
