"""Public experiment receipt is a closed numeric protocol, not a log channel."""
import importlib.util
import json
from pathlib import Path
import pytest

PATH=Path(__file__).resolve().parents[2]/'scripts/real_cpu_report.py'

def load():
    assert PATH.is_file(), 'closed real experiment report is not implemented'
    spec=importlib.util.spec_from_file_location('real_report',PATH)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_not_run_is_not_zero_or_success():
    m=load();value=m.initial()
    assert value['status']=='failed'
    assert all(x['status']=='NOT_RUN' for x in value['stages'])
    assert value['measurements'] is None
    assert m.validate(json.dumps(value))==value


def test_finite_raw_measurements_recomputed_not_trusted():
    m=load();raw=list(range(1,21))
    assert m.statistics(raw)=={'median_ms':10.5,'p95_ms':19}
    for values in ([1]*19,[1]*21,[True]*20,[float('nan')]*20,[-1]*20,[float('inf')]*20,[600001]*20):
        with pytest.raises(ValueError):m.statistics(values)


@pytest.mark.parametrize('bad',['field','stage','success','duplicate','schema','measurements'])
def test_closed_failure_protocol(bad):
    m=load();v=m.initial()
    if bad=='field':v['private_path']='secret'
    if bad=='stage':v['stages'][0]['stage']='arbitrary'
    if bad=='success':v['status']='passed'
    if bad=='schema':v['schema_version']=True
    if bad=='measurements':v['measurements']={}
    raw=json.dumps(v)
    if bad=='duplicate':raw=raw[:-1]+',"status":"failed"}'
    with pytest.raises(ValueError):m.validate(raw)


def test_complete_requires_every_gate_and_frozen_dataset():
    m=load();v=m.initial()
    for x in v['stages']:x['status']='passed'
    v['status']='passed'
    with pytest.raises(ValueError):m.validate(json.dumps(v))
    v['measurements']=m.measurements({key:list(range(1,21)) for key in m.SERIES},{'pt':1.,'onnx':1.})
    v['evaluation']={'protocol':'single-head-p025-iou050-v1',**{b:{'images':20,'ground_truth':20,'tp':0,'fp':0,'fn':20,'precision':0.,'recall':0.} for b in ('pt','onnx')}}
    v['evaluation']['comparison']={'images':20,'elements':1008000,'max_absolute_error':0.,'max_tolerance_ratio':0.,'atol':1e-4,'rtol':1e-4,'detections_matched':True}
    assert m.validate(json.dumps(v))==v
    v['measurements']['series']['pt_total']['summary']['p95_ms']=18
    with pytest.raises(ValueError):m.validate(json.dumps(v))

@pytest.mark.parametrize('bad',['hash','raw_bool','summary_bool','extra_series','sample_bool','without_gate','too_large'])
def test_numeric_receipt_rejects_ambiguous_or_unbounded_values(bad):
    m=load();v=m.initial()
    for stage in v['stages']:stage['status']='passed'
    v['measurements']=m.measurements({key:[1]*20 for key in m.SERIES},{'pt':1.,'onnx':1.})
    v['evaluation']={'protocol':'single-head-p025-iou050-v1',**{b:{'images':20,'ground_truth':20,'tp':0,'fp':0,'fn':20,'precision':0.,'recall':0.} for b in ('pt','onnx')}}
    v['evaluation']['comparison']={'images':20,'elements':1008000,'max_absolute_error':0.,'max_tolerance_ratio':0.,'atol':1e-4,'rtol':1e-4,'detections_matched':True}
    if bad=='hash':v['manifest_sha256']='0'*64
    if bad=='raw_bool':v['measurements']['series']['pt_total']['raw'][0]=True
    if bad=='summary_bool':v['measurements']['series']['pt_total']['summary']['median_ms']=True
    if bad=='extra_series':v['measurements']['series']['filename']={}
    if bad=='sample_bool':v['measurements']['samples']=True
    if bad=='without_gate':v['stages'][m.STAGES.index('timings')]['status']='NOT_RUN'
    raw=json.dumps(v)
    if bad=='too_large':raw+=' '*16384
    with pytest.raises(ValueError):m.validate(raw)


def test_evaluation_requires_closed_consistent_counts():
    m=load();v=m.initial()
    assert 'evaluation' in v
    for stage in v['stages']:stage['status']='passed'
    v['evaluation']={'protocol':'single-head-p025-iou050-v1','pt':{'images':20,'ground_truth':20,'tp':0,'fp':0,'fn':20,'precision':0.,'recall':0.},'onnx':{'images':20,'ground_truth':20,'tp':0,'fp':0,'fn':20,'precision':0.,'recall':0.}}
    v['evaluation']['comparison']={'images':20,'elements':1008000,'max_absolute_error':0.,'max_tolerance_ratio':0.,'atol':1e-4,'rtol':1e-4,'detections_matched':True}
    assert m.validate(json.dumps(v))==v
    v['evaluation']['pt']['precision']=1.
    with pytest.raises(ValueError):m.validate(json.dumps(v))


def test_evaluation_cannot_claim_comparison_without_bounded_proof():
    m=load();v=m.initial()
    for stage in v['stages']:stage['status']='passed'
    v['evaluation']={'protocol':'single-head-p025-iou050-v1',**{b:{'images':20,'ground_truth':20,'tp':0,'fp':0,'fn':20,'precision':0.,'recall':0.} for b in ('pt','onnx')}}
    with pytest.raises(ValueError):m.validate(json.dumps(v))


def test_load_cost_is_separate_from_twenty_samples():
    m=load()
    result=m.measurements({key:[1]*20 for key in m.SERIES},{'pt':100.,'onnx':20.})
    assert result['model_load_ms']=={'pt':100.,'onnx':20.}
    with pytest.raises(ValueError):m.measurements({key:[1]*20 for key in m.SERIES},{'pt':True,'onnx':20.})
